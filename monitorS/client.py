#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工监控系统客户端 - 完整工业级增强版
功能：
1. 健康监控系统
2. 上传队列系统
3. 缓冲区池系统
4. 指数退避重试系统
5. 多显示器截图功能
6. 感知哈希相似度检测
7. 增强的托盘图标功能
8. 配置版本升级和备份
9. 进程看门狗系统
10. 原子文件操作
"""

import os
import sys
import time
import json
import socket
import uuid
import logging
import argparse
import platform
import hashlib
import threading
import io
import zipfile
import random
import queue
import math
import tempfile
import shutil
import signal
import psutil
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum

import requests
from PIL import ImageGrab, Image

# 导入工具模块
from client_utils import (
    SystemInfoCollector,
    ConfigManager,
    TrayIcon,
    retry,
    setup_logging,
    AutoConfig,
)
from client_config import Config

setup_logging(log_level=logging.INFO, log_file="monitor.log")

# ========== 依赖检查 ==========
PYSTRAY_AVAILABLE = False
PLYER_AVAILABLE = False

try:
    import pystray
    from PIL import ImageDraw

    PYSTRAY_AVAILABLE = True
except ImportError:
    pass

try:
    from plyer import notification

    PLYER_AVAILABLE = True
except ImportError:
    pass

# 检查 psutil（如果使用）
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("⚠️ psutil未安装，看门狗健康检查功能受限")


# ========== 枚举定义 ==========
class HealthStatus(Enum):
    """健康状态枚举"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# ========== 数据类定义 ==========
@dataclass
class HealthRecord:
    """健康记录数据类"""

    timestamp: float
    component: str
    status: HealthStatus
    message: str = ""
    response_time: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentHealth:
    """组件健康状态数据类"""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check_time: float = 0.0
    last_healthy_time: float = 0.0
    failure_count: int = 0
    recovery_count: int = 0
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UploadTask:
    """上传任务数据类"""

    image_data: bytes
    filename: str
    employee_id: str
    client_id: str
    timestamp: str
    computer_name: str
    windows_user: str
    format: str
    encrypted: bool = False  # 修复：添加 encrypted 字段，默认为 False
    retry_count: int = 0
    last_attempt: float = 0.0


# ========== 原子文件操作 ==========
class AtomicFileOperation:
    """原子文件操作类 - 确保文件操作的完整性"""

    @staticmethod
    def atomic_write(filepath: str, data: bytes, mode: str = "wb") -> bool:
        """原子写入文件（使用临时文件）"""
        try:
            filepath = Path(filepath)
            # 确保目录存在
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # 创建临时文件
            with tempfile.NamedTemporaryFile(
                mode=mode,
                dir=filepath.parent,
                prefix=".tmp_",
                suffix=filepath.suffix,
                delete=False,
            ) as tmp_file:
                tmp_file.write(data)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())  # 确保写入磁盘
                tmp_path = tmp_file.name

            # 原子重命名
            shutil.move(tmp_path, filepath)
            return True

        except Exception as e:
            logging.getLogger(__name__).error(f"原子写入失败 {filepath}: {e}")
            # 清理临时文件
            try:
                if "tmp_path" in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except:
                pass
            return False

    @staticmethod
    def atomic_read(filepath: str) -> Optional[bytes]:
        """原子读取文件"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                return None

            # 读取临时文件时跳过
            if filepath.name.startswith(".tmp_"):
                return None

            with open(filepath, "rb") as f:
                return f.read()
        except Exception as e:
            logging.getLogger(__name__).error(f"原子读取失败 {filepath}: {e}")
            return None

    @staticmethod
    def atomic_delete(filepath: str) -> bool:
        """原子删除文件"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                return True

            # 先重命名为临时文件，再删除
            tmp_path = filepath.parent / f".tmp_del_{filepath.name}"
            shutil.move(str(filepath), str(tmp_path))
            os.unlink(tmp_path)
            return True
        except Exception as e:
            logging.getLogger(__name__).error(f"原子删除失败 {filepath}: {e}")
            return False

    @staticmethod
    def atomic_rename(src: str, dst: str) -> bool:
        """原子重命名"""
        try:
            src_path = Path(src)
            dst_path = Path(dst)

            if not src_path.exists():
                return False

            # 确保目标目录存在
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            # 使用临时文件作为中间步骤
            tmp_path = dst_path.parent / f".tmp_mv_{dst_path.name}"
            shutil.move(str(src_path), str(tmp_path))
            shutil.move(str(tmp_path), str(dst_path))
            return True
        except Exception as e:
            logging.getLogger(__name__).error(f"原子重命名失败 {src} -> {dst}: {e}")
            return False


# ========== 缓冲区池系统 ==========
class BufferPool:
    """缓冲区池单例类"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, max_size: int = 10, buffer_size: int = 10 * 1024 * 1024):
        """初始化缓冲区池

        Args:
            max_size: 池中最大缓冲区数量
            buffer_size: 每个缓冲区的初始大小（字节）
        """
        if self._initialized:
            return
        self._initialized = True

        self.max_size = max_size
        self.buffer_size = buffer_size
        self.pool = queue.Queue(maxsize=max_size)
        self.stats = {
            "created": 0,
            "acquired": 0,
            "released": 0,
            "discarded": 0,
            "pool_empty": 0,
        }
        self.stats_lock = threading.RLock()

        # 预创建部分缓冲区
        for _ in range(max_size // 2):
            self._create_buffer()

    def _create_buffer(self) -> io.BytesIO:
        """创建新缓冲区"""
        buffer = io.BytesIO()
        buffer.seek(0)
        buffer.truncate(0)
        with self.stats_lock:
            self.stats["created"] += 1
        return buffer

    def acquire(self) -> io.BytesIO:
        """获取缓冲区"""
        try:
            buffer = self.pool.get_nowait()
            with self.stats_lock:
                self.stats["acquired"] += 1
        except queue.Empty:
            buffer = self._create_buffer()
            with self.stats_lock:
                self.stats["pool_empty"] += 1
                self.stats["acquired"] += 1

        # 重置缓冲区
        buffer.seek(0)
        buffer.truncate(0)
        return buffer

    def release(self, buffer: io.BytesIO):
        """释放缓冲区"""
        try:
            # 重置缓冲区
            buffer.seek(0)
            buffer.truncate(0)
            # 尝试放回池中
            self.pool.put_nowait(buffer)
            with self.stats_lock:
                self.stats["released"] += 1
        except queue.Full:
            # 池已满，丢弃缓冲区
            with self.stats_lock:
                self.stats["discarded"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.stats_lock:
            return {
                **self.stats.copy(),
                "pool_size": self.pool.qsize(),
                "max_size": self.max_size,
            }


# 全局缓冲区池访问函数
_buffer_pool = None


def get_buffer_pool() -> BufferPool:
    """获取缓冲区池单例"""
    global _buffer_pool
    if _buffer_pool is None:
        _buffer_pool = BufferPool()
    return _buffer_pool


def get_buffer() -> io.BytesIO:
    """获取缓冲区（便捷函数）"""
    return get_buffer_pool().acquire()


def put_buffer(buffer: io.BytesIO):
    """释放缓冲区（便捷函数）"""
    get_buffer_pool().release(buffer)


# ========== 进程看门狗系统 ==========
class ProcessWatchdog:
    """进程看门狗 - 监控和恢复子进程"""

    def __init__(self, check_interval: int = 30, max_restarts: int = 5):
        self.check_interval = check_interval
        self.max_restarts = max_restarts
        self.watched_processes: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.running = False
        self.watchdog_thread = None
        self.logger = logging.getLogger(__name__)

        # 统计信息
        self.stats = {
            "total_restarts": 0,
            "failed_restarts": 0,
            "total_health_check_failures": 0,
            "last_check": None,
        }

        # 注册信号处理
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """设置信号处理"""
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (ValueError, AttributeError):
            # 非主线程中无法设置信号处理
            pass

    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        self.logger.info(f"接收到信号 {signum}，停止看门狗")
        self.stop()

    def watch(
        self,
        name: str,
        process_func: callable,
        args: tuple = (),
        kwargs: dict = None,
        auto_restart: bool = True,
        health_check: callable = None,
        health_check_interval: int = 60,
    ):
        """监控一个进程 - 添加重复检查"""
        with self.lock:
            # 检查是否已经存在同名进程
            if name in self.watched_processes:
                self.logger.warning(f"进程 {name} 已经存在，跳过重复注册")
                return False

            self.watched_processes[name] = {
                "func": process_func,
                "args": args,
                "kwargs": kwargs or {},
                "auto_restart": auto_restart,
                "health_check": health_check,
                "health_check_interval": health_check_interval,
                "last_health_check": 0,
                "health_check_failures": 0,
                "thread": None,
                "restart_count": 0,
                "last_restart": 0,
                "status": "stopped",
                "error": None,
                "pid": None,
                "stop_event": threading.Event(),
                "last_heartbeat": time.time(),
                "failure_count": 0,
            }
            self.logger.info(f"✅ 进程已加入看门狗监控: {name}")
            return True

    def start_watch(self, name: str):
        """启动监控指定进程"""
        with self.lock:
            if name not in self.watched_processes:
                self.logger.error(f"进程 {name} 不存在")
                return False

            process_info = self.watched_processes[name]

            # 检查是否已达到最大重启次数
            if process_info["restart_count"] >= self.max_restarts:
                self.logger.error(
                    f"进程 {name} 已达到最大重启次数 ({self.max_restarts})"
                )
                process_info["status"] = "failed"
                return False

            # 检查冷却时间
            if process_info["last_restart"] > 0:
                cooldown = 60  # 60秒冷却
                if time.time() - process_info["last_restart"] < cooldown:
                    self.logger.debug(f"进程 {name} 处于重启冷却期，跳过")
                    return False

            # 重置停止事件
            process_info["stop_event"].clear()

            # 启动进程
            try:
                thread = threading.Thread(
                    target=self._run_process,
                    name=f"Watchdog-{name}",
                    args=(name,),
                    daemon=True,
                )
                thread.start()

                process_info["thread"] = thread
                process_info["status"] = "running"
                process_info["restart_count"] += 1
                process_info["last_restart"] = time.time()
                process_info["pid"] = thread.ident
                process_info["last_health_check"] = time.time()
                process_info["health_check_failures"] = 0

                self.logger.info(
                    f"🔄 看门狗启动进程: {name} (重启 #{process_info['restart_count']})"
                )
                return True

            except Exception as e:
                self.logger.error(f"启动进程 {name} 失败: {e}")
                process_info["status"] = "error"
                process_info["error"] = str(e)
                with self.lock:
                    self.stats["failed_restarts"] += 1
                return False

    def _run_process(self, name: str):
        """运行被监控的进程"""
        process_info = self.watched_processes[name]

        try:
            # 执行进程函数
            process_info["func"](*process_info["args"], **process_info["kwargs"])
        except Exception as e:
            # 检查是否是停止事件导致的退出
            if process_info["stop_event"].is_set():
                self.logger.info(f"进程 {name} 被停止")
                process_info["status"] = "stopped"
            else:
                self.logger.error(f"进程 {name} 异常退出: {e}")
                process_info["error"] = str(e)
                process_info["status"] = "crashed"

                # 自动重启
                if process_info["auto_restart"]:
                    self.logger.info(f"⏳ 等待5秒后重启进程 {name}")
                    time.sleep(5)  # 等待5秒后重启
                    self.start_watch(name)
        else:
            # 正常退出
            process_info["status"] = "stopped"
            self.logger.info(f"进程 {name} 正常退出")

    def heartbeat(self, name: str):
        """更新组件心跳"""
        with self.lock:
            if name in self.watched_processes:
                self.watched_processes[name]["last_heartbeat"] = time.time()
                self.watched_processes[name]["failure_count"] = 0
                self.watched_processes[name]["health_check_failures"] = 0
                self.logger.debug(f"看门狗心跳: {name}")

    def stop_watch(self, name: str):
        """停止监控指定进程"""
        with self.lock:
            if name not in self.watched_processes:
                return

            process_info = self.watched_processes[name]
            process_info["auto_restart"] = False
            process_info["status"] = "stopping"

            # 发送停止事件
            process_info["stop_event"].set()

            # 等待线程结束
            thread = process_info.get("thread")
            if thread and thread.is_alive():
                thread.join(timeout=10)

            process_info["status"] = "stopped"
            process_info["thread"] = None
            process_info["pid"] = None
            self.logger.info(f"⏹️ 看门狗停止进程: {name}")

    def health_check(self, name: str) -> bool:
        """检查指定进程的健康状态"""
        with self.lock:
            if name not in self.watched_processes:
                return False

            process_info = self.watched_processes[name]

            # 检查线程状态
            thread = process_info.get("thread")
            if not thread or not thread.is_alive():
                return False

            # 调用自定义健康检查
            health_check = process_info.get("health_check")
            if health_check:
                try:
                    return health_check()
                except Exception as e:
                    self.logger.error(f"健康检查函数异常 {name}: {e}")
                    return False

            return True

    def perform_health_check(self, name: str) -> bool:
        with self.lock:
            if name not in self.watched_processes:
                return False

            process_info = self.watched_processes[name]
            process_info["last_health_check"] = time.time()
            is_healthy = self.health_check(name)

            should_restart = False
            if not is_healthy:
                process_info["health_check_failures"] += 1
                self.logger.warning(
                    f"⚠️ 进程 {name} 健康检查失败 "
                    f"(第{process_info['health_check_failures']}次)"
                )
                if process_info["health_check_failures"] >= 3:
                    self.logger.error(f"❌ 进程 {name} 连续3次健康检查失败，准备重启")
                    self.stats["total_health_check_failures"] += 1
                    should_restart = True
            else:
                if process_info["health_check_failures"] > 0:
                    self.logger.info(f"✅ 进程 {name} 健康检查恢复")
                process_info["health_check_failures"] = 0

        # 在锁外执行重启
        if should_restart:
            self._restart_process(name)

        return is_healthy

    def _restart_process(self, name: str):
        """重启进程"""
        with self.lock:
            if name not in self.watched_processes:
                return

            process_info = self.watched_processes[name]

            # 检查是否允许重启
            if not process_info["auto_restart"]:
                self.logger.info(f"进程 {name} 未启用自动重启，跳过")
                return

            # 检查是否已达到最大重启次数
            if process_info["restart_count"] >= self.max_restarts:
                self.logger.error(f"进程 {name} 已达到最大重启次数，不再重启")
                process_info["status"] = "failed"
                return

            self.logger.info(f"🔄 正在重启进程: {name}")

            # 先停止旧进程
            old_thread = process_info.get("thread")
            if old_thread and old_thread.is_alive():
                process_info["stop_event"].set()
                old_thread.join(timeout=5)

            # 重置状态
            process_info["stop_event"].clear()
            process_info["thread"] = None
            process_info["pid"] = None
            process_info["status"] = "stopped"

            # 启动新进程
            self.start_watch(name)

            # 更新统计
            self.stats["total_restarts"] += 1

    def start(self):
        """启动看门狗监控线程"""
        if self.running:
            return

        self.running = True
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="ProcessWatchdog", daemon=True
        )
        self.watchdog_thread.start()
        self.logger.info("✅ 进程看门狗已启动")

    def stop(self):
        """停止看门狗"""
        self.logger.info("⏹️ 正在停止看门狗...")
        self.running = False

        if self.watchdog_thread and self.watchdog_thread.is_alive():
            self.watchdog_thread.join(timeout=5)

        # 停止所有被监控进程
        with self.lock:
            for name in list(self.watched_processes.keys()):
                self.stop_watch(name)

        self.logger.info("⏹️ 进程看门狗已停止")

    def clear_config(self):
        """清除本地配置（用于重新配置）"""
        self.logger.info("🧹 清除本地配置")
        self.config_manager.set("employee_name", "")
        self.config_manager.set("client_id", "")
        self.config_manager.set("employee_id", "")
        self.first_run = True
        self._force_reconfigure = True

    def get_status(self) -> Dict[str, Any]:
        """获取看门狗状态"""
        with self.lock:
            processes = {}
            for name, info in self.watched_processes.items():
                processes[name] = {
                    "status": info["status"],
                    "restart_count": info["restart_count"],
                    "pid": info["pid"],
                    "error": info["error"],
                    "auto_restart": info["auto_restart"],
                    "alive": (
                        info["thread"] and info["thread"].is_alive()
                        if info["thread"]
                        else False
                    ),
                    "health_check_failures": info.get("health_check_failures", 0),
                    "last_health_check": info.get("last_health_check", 0),
                }

            return {
                "running": self.running,
                "processes": processes,
                "stats": self.stats.copy(),
            }

    def is_process_healthy(self, name: str) -> bool:
        """快速检查进程是否健康（对外接口）"""
        return self.health_check(name)

    def get_process_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定进程信息"""
        with self.lock:
            if name not in self.watched_processes:
                return None
            return self.watched_processes[name].copy()

    def _watchdog_loop(self):
        """看门狗主循环"""
        while self.running:
            try:
                self.stats["last_check"] = time.time()
                now = time.time()

                with self.lock:
                    for name, process_info in list(self.watched_processes.items()):
                        # 只检查自动重启的进程
                        if not process_info["auto_restart"]:
                            continue

                        # 检查进程线程状态
                        thread = process_info.get("thread")

                        # 情况1：线程不存在或已停止
                        if not thread or not thread.is_alive():
                            self.logger.warning(f"⚠️ 进程 {name} 线程已停止，准备重启")
                            self._restart_process(name)
                            continue

                        # 情况2：需要执行健康检查
                        health_check = process_info.get("health_check")
                        health_check_interval = process_info.get(
                            "health_check_interval", 60
                        )
                        last_health_check = process_info.get("last_health_check", 0)

                        if health_check and (
                            now - last_health_check >= health_check_interval
                        ):
                            # 在独立线程中执行健康检查，避免阻塞看门狗
                            threading.Thread(
                                target=self.perform_health_check,
                                args=(name,),
                                daemon=True,
                            ).start()

                time.sleep(self.check_interval)

            except Exception as e:
                self.logger.error(f"看门狗循环异常: {e}", exc_info=True)
                time.sleep(30)

    def report_failure(self, name: str, error: str = ""):
        """报告组件失败（兼容性方法）"""
        with self.lock:
            if name in self.watched_processes:
                self.watched_processes[name]["failure_count"] = (
                    self.watched_processes[name].get("failure_count", 0) + 1
                )
                self.watched_processes[name]["last_error"] = error
                self.watched_processes[name]["last_failure"] = time.time()
                self.logger.debug(f"组件 {name} 报告失败: {error}")

                # 如果失败次数过多，触发重启
                if self.watched_processes[name]["failure_count"] >= 3:
                    self.logger.warning(f"组件 {name} 连续失败3次，准备重启进程")
                    self._restart_process(name)


# ========== 健康监控系统 ==========
class HealthHistory:
    """健康历史记录管理器"""

    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self.records = deque(maxlen=max_records)
        self.lock = threading.RLock()

    def add_record(self, record: HealthRecord):
        """添加健康记录"""
        with self.lock:
            self.records.append(record)

    def get_recent(self, count: int = 10) -> List[HealthRecord]:
        """获取最近N条记录"""
        with self.lock:
            return list(self.records)[-count:]

    def get_component_stats(self, component: str, minutes: int = 60) -> Dict[str, Any]:
        """获取组件统计信息"""
        cutoff = time.time() - minutes * 60
        records = []

        with self.lock:
            for record in self.records:
                if record.component == component and record.timestamp >= cutoff:
                    records.append(record)

        if not records:
            return {}

        total = len(records)
        healthy = sum(1 for r in records if r.status == HealthStatus.HEALTHY)
        degraded = sum(1 for r in records if r.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for r in records if r.status == HealthStatus.UNHEALTHY)

        return {
            "total": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "health_rate": healthy / total if total > 0 else 0,
            "avg_response_time": (
                sum(r.response_time for r in records) / total if total > 0 else 0
            ),
        }


class HealthMonitor:
    """健康监控主类"""

    def __init__(self, check_interval: int = 60, recovery_cooldown: int = 300):
        self.components: Dict[str, ComponentHealth] = {}
        self.history = HealthHistory()
        self.lock = threading.RLock()
        self.check_interval = check_interval
        self.recovery_cooldown = recovery_cooldown
        self.last_recovery_time: Dict[str, float] = {}
        self.running = False
        self.monitor_thread = None
        self.logger = logging.getLogger(__name__)
        self.recovery_callbacks: Dict[str, List[callable]] = {}

    def register_component(self, name: str, recovery_callback: callable = None):
        """注册监控组件"""
        with self.lock:
            if name not in self.components:
                self.components[name] = ComponentHealth(name=name)
                if recovery_callback:
                    self.recovery_callbacks.setdefault(name, []).append(
                        recovery_callback
                    )
                self.logger.info(f"✅ 组件已注册到健康监控: {name}")

    def update_status(
        self,
        component: str,
        status: HealthStatus,
        message: str = "",
        response_time: float = 0.0,
        metrics: Dict[str, Any] = None,
    ):
        """更新组件状态"""
        with self.lock:
            if component not in self.components:
                self.logger.warning(f"尝试更新未注册的组件: {component}")
                return

            comp = self.components[component]
            now = time.time()

            # 更新组件状态
            comp.status = status
            comp.last_check_time = now
            comp.message = message
            if metrics:
                comp.metrics.update(metrics)

            if status == HealthStatus.HEALTHY:
                comp.last_healthy_time = now
                comp.failure_count = 0
            elif status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]:
                comp.failure_count += 1

            # 创建健康记录
            record = HealthRecord(
                timestamp=now,
                component=component,
                status=status,
                message=message,
                response_time=response_time,
                details=metrics or {},
            )
            self.history.add_record(record)

            # 检查是否需要触发恢复
            if comp.failure_count >= 3:
                self._trigger_recovery(component)

    def _trigger_recovery(self, component: str):
        """触发组件恢复"""
        now = time.time()
        last_recovery = self.last_recovery_time.get(component, 0)

        # 检查冷却时间
        if now - last_recovery < self.recovery_cooldown:
            self.logger.debug(f"组件 {component} 处于恢复冷却期，跳过")
            return

        self.last_recovery_time[component] = now
        self.components[component].recovery_count += 1

        self.logger.warning(
            f"🔄 触发组件恢复: {component} (第{self.components[component].recovery_count}次)"
        )

        # 调用恢复回调
        callbacks = self.recovery_callbacks.get(component, [])
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"恢复回调执行失败: {e}")

    def get_component_status(self, component: str) -> Optional[ComponentHealth]:
        """获取组件状态"""
        with self.lock:
            return self.components.get(component)

    def get_all_status(self) -> Dict[str, ComponentHealth]:
        """获取所有组件状态"""
        with self.lock:
            return self.components.copy()

    def get_summary(self) -> Dict[str, Any]:
        """获取健康状态摘要"""
        with self.lock:
            total = len(self.components)
            healthy = sum(
                1 for c in self.components.values() if c.status == HealthStatus.HEALTHY
            )
            degraded = sum(
                1 for c in self.components.values() if c.status == HealthStatus.DEGRADED
            )
            unhealthy = sum(
                1
                for c in self.components.values()
                if c.status == HealthStatus.UNHEALTHY
            )
            unknown = sum(
                1 for c in self.components.values() if c.status == HealthStatus.UNKNOWN
            )

            return {
                "total": total,
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "unknown": unknown,
                "health_rate": healthy / total if total > 0 else 0,
                "total_recoveries": sum(
                    c.recovery_count for c in self.components.values()
                ),
            }

    def start_monitoring(self):
        """启动健康监控线程"""
        if self.running:
            return

        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, name="HealthMonitor", daemon=True
        )
        self.monitor_thread.start()
        self.logger.info("✅ 健康监控线程已启动")

    def stop_monitoring(self):
        """停止健康监控"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

    def _monitor_loop(self):
        """健康监控主循环"""
        while self.running:
            try:
                now = time.time()

                # 检查各组件状态
                with self.lock:
                    for name, comp in self.components.items():
                        # 检查是否超时（超过3个检查周期未更新）
                        if now - comp.last_check_time > self.check_interval * 3:
                            self.logger.warning(f"组件 {name} 状态更新超时")
                            comp.status = HealthStatus.UNKNOWN

                time.sleep(self.check_interval)

            except Exception as e:
                self.logger.error(f"健康监控循环出错: {e}")
                time.sleep(30)


# ========== 上传队列系统 ==========
class UploadQueue:
    """上传队列管理器"""

    def __init__(
        self,
        client,
        max_queue_size: int = 100,
        worker_count: int = 3,
        cache_dir: str = "cache",
        max_cache_size: int = 500 * 1024 * 1024,
    ):  # 500MB
        self.client = client
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.workers = []
        self.running = False
        self.logger = logging.getLogger(__name__)
        self.lock = threading.RLock()

        # 统计信息
        self.stats = {
            "enqueued": 0,
            "processed": 0,
            "failed": 0,
            "retried": 0,
            "discarded": 0,
            "queue_full": 0,
            "cache_saved": 0,
            "cache_loaded": 0,
        }

        # 缓存配置
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.max_cache_size = max_cache_size

        # 工作线程配置
        self.worker_count = worker_count

        # 重试配置
        self.base_delay = 5
        self.max_delay = 120

        # 监控线程
        self.monitor_thread = None

    def start(self):
        """启动队列系统"""
        if self.running:
            return

        self.running = True

        # 启动工作线程
        for i in range(self.worker_count):
            worker = threading.Thread(
                target=self._worker_loop, name=f"UploadWorker-{i}", daemon=True
            )
            worker.start()
            self.workers.append(worker)

        # 启动监控线程
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, name="QueueMonitor", daemon=True
        )
        self.monitor_thread.start()

        # 加载缓存的失败任务
        self._load_cached_tasks()

        self.logger.info(f"✅ 上传队列系统已启动 (工作线程: {self.worker_count})")

    def stop(self):
        """停止队列系统"""
        self.running = False

        # 等待队列处理完成
        if not self.queue.empty():
            self.logger.info(f"等待队列处理完成，剩余任务: {self.queue.qsize()}")
            timeout = 30
            while not self.queue.empty() and timeout > 0:
                time.sleep(1)
                timeout -= 1

    def enqueue(self, task: UploadTask) -> bool:
        """添加任务到队列"""
        try:
            self.queue.put_nowait(task)
            with self.lock:
                self.stats["enqueued"] += 1
            return True
        except queue.Full:
            # 队列已满，保存到缓存
            self._save_to_cache(task)
            with self.lock:
                self.stats["queue_full"] += 1
                self.stats["cache_saved"] += 1
            return False

    def _worker_loop(self):
        """工作线程主循环"""
        while self.running:
            try:
                # 获取任务（超时1秒以便检查运行状态）
                try:
                    task = self.queue.get(timeout=1)
                except queue.Empty:
                    continue

                # 处理任务
                self._process_task(task)

                # 标记任务完成
                self.queue.task_done()

            except Exception as e:
                self.logger.error(f"工作线程异常: {e}")
                time.sleep(1)

    def _process_task(self, task: UploadTask):
        """处理上传任务"""
        try:
            # 计算重试延迟（指数退避）
            if task.retry_count > 0:
                delay = min(
                    self.base_delay * (2 ** (task.retry_count - 1)), self.max_delay
                )
                # 添加随机抖动
                delay += random.uniform(0, 5)

                # 检查是否到达重试时间
                if time.time() - task.last_attempt < delay:
                    # 重新放回队列
                    self.enqueue(task)
                    return

            # 执行上传
            task.last_attempt = time.time()
            success = self._upload_task(task)

            if success:
                with self.lock:
                    self.stats["processed"] += 1
                self.logger.debug(f"✅ 任务上传成功: {task.filename}")
            else:
                task.retry_count += 1

                # 检查重试次数
                if task.retry_count < self.client.retry_times:
                    with self.lock:
                        self.stats["retried"] += 1
                    # 重新入队重试
                    self.enqueue(task)
                    self.logger.debug(
                        f"↻ 任务重试 ({task.retry_count}/{self.client.retry_times}): {task.filename}"
                    )
                else:
                    with self.lock:
                        self.stats["failed"] += 1
                    self._save_to_cache(task)
                    self.logger.warning(f"⚠️ 任务失败，已缓存: {task.filename}")

        except Exception as e:
            self.logger.error(f"处理任务异常: {e}")
            with self.lock:
                self.stats["failed"] += 1
            self._save_to_cache(task)

    def _upload_task(self, task: UploadTask) -> bool:
        """执行实际的上传"""
        try:
            buffer = get_buffer()

            # 准备文件和数据
            files = {
                "file": (
                    task.filename,
                    io.BytesIO(task.image_data),
                    f"image/{task.format}",
                )
            }

            # 修复：使用 task.encrypted 动态设置 encrypted 字段
            data = {
                "employee_id": task.employee_id,
                "client_id": task.client_id,
                "timestamp": task.timestamp,
                "computer_name": task.computer_name,
                "windows_user": task.windows_user,
                "encrypted": str(task.encrypted).lower(),  # 修复：使用实际值
                "format": task.format,
            }

            # 发送请求
            response = self.client.api_client.session.post(
                f"{self.client.current_server}/api/upload",
                files=files,
                data=data,
                timeout=60,
            )

            if response.status_code == 200:
                return True
            else:
                self.logger.warning(f"上传失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.debug(f"上传异常: {e}")
            return False
        finally:
            put_buffer(buffer)

    def _save_to_cache(self, task: UploadTask):
        """保存任务到磁盘缓存（使用原子操作）"""
        try:
            cache_file = self.cache_dir / task.filename
            AtomicFileOperation.atomic_write(str(cache_file), task.image_data)

            # 清理缓存（如果超过限制）
            self._cleanup_cache()

        except Exception as e:
            self.logger.error(f"保存到缓存失败: {e}")

    def _load_cached_tasks(self):
        """加载缓存的失败任务（使用原子操作）"""
        try:
            count = 0
            for cache_file in self.cache_dir.glob("screenshot_*"):
                if cache_file.stat().st_size == 0:
                    AtomicFileOperation.atomic_delete(str(cache_file))
                    continue

                try:
                    # 使用原子读取
                    image_data = AtomicFileOperation.atomic_read(str(cache_file))
                    if image_data is None:
                        continue

                    # 解析文件名
                    parts = cache_file.stem.split("_")
                    if len(parts) < 2:
                        continue

                    # 修复：解析文件名中的加密状态
                    encrypted = False
                    if "encrypted" in cache_file.suffixes:
                        encrypted = True

                    task = UploadTask(
                        image_data=image_data,
                        filename=cache_file.name,
                        employee_id=self.client.employee_id,
                        client_id=self.client.client_id,
                        timestamp=parts[1] + "_" + parts[2] if len(parts) > 2 else "",
                        computer_name=self.client.system_info.get_computer_name(),
                        windows_user=self.client.system_info.get_windows_user(),
                        format=cache_file.suffix[1:] or "webp",
                        encrypted=encrypted,  # 修复：设置加密状态
                    )

                    # 重新入队
                    self.enqueue(task)
                    count += 1

                    # 删除缓存文件
                    AtomicFileOperation.atomic_delete(str(cache_file))

                except Exception as e:
                    self.logger.error(f"加载缓存文件失败 {cache_file}: {e}")

            if count > 0:
                self.logger.info(f"📦 从缓存加载了 {count} 个待上传任务")
                with self.lock:
                    self.stats["cache_loaded"] = count

        except Exception as e:
            self.logger.error(f"加载缓存失败: {e}")

    def _cleanup_cache(self):
        """清理缓存目录（超过限制时删除最旧的20%）"""
        try:
            # 计算总大小
            total_size = 0
            files = []

            for cache_file in self.cache_dir.glob("*"):
                if cache_file.is_file() and not cache_file.name.startswith(".tmp_"):
                    size = cache_file.stat().st_size
                    total_size += size
                    files.append((cache_file, cache_file.stat().st_mtime, size))

            # 如果超过限制，删除最旧的20%
            if total_size > self.max_cache_size:
                # 按修改时间排序（最旧的在前）
                files.sort(key=lambda x: x[1])

                # 计算需要删除的大小（超过限制的部分）
                target_size = total_size - self.max_cache_size * 0.8
                deleted_size = 0
                deleted_count = 0

                for cache_file, _, size in files:
                    if deleted_size >= target_size:
                        break

                    if AtomicFileOperation.atomic_delete(str(cache_file)):
                        deleted_size += size
                        deleted_count += 1

                self.logger.info(
                    f"🧹 缓存清理: 删除了 {deleted_count} 个文件，释放 {deleted_size/1024/1024:.1f}MB"
                )

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")

    def _monitor_loop(self):
        """队列监控线程"""
        while self.running:
            try:
                queue_size = self.queue.qsize()
                queue_percent = (queue_size / self.queue.maxsize) * 100

                # 队列使用率警告
                if queue_percent > 80:
                    self.logger.warning(
                        f"⚠️ 上传队列使用率: {queue_percent:.1f}% ({queue_size}/{self.queue.maxsize})"
                    )

                # 记录统计信息
                self.logger.debug(
                    f"队列状态 - 大小: {queue_size}, 已处理: {self.stats['processed']}, 失败: {self.stats['failed']}"
                )

                time.sleep(30)

            except Exception as e:
                self.logger.error(f"队列监控异常: {e}")
                time.sleep(30)

    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        with self.lock:
            return {
                **self.stats.copy(),
                "queue_size": self.queue.qsize(),
                "queue_maxsize": self.queue.maxsize,
                "cache_size": sum(
                    f.stat().st_size for f in self.cache_dir.glob("*") if f.is_file()
                ),
                "cache_count": len(list(self.cache_dir.glob("*"))),
            }


# ========== 多显示器截图功能 ==========
class MultiMonitorScreenshot:
    """多显示器截图处理器"""

    def __init__(self):
        self.has_mss = False
        self.logger = logging.getLogger(__name__)

        # 尝试导入 mss
        try:
            import mss

            self.mss = mss
            self.has_mss = True
            self.logger.info("✅ 已启用多显示器截图支持 (mss)")
        except ImportError:
            self.logger.warning("⚠️ mss未安装，使用单显示器模式 (PIL)")

    def capture_all_monitors(self) -> Optional[Image.Image]:
        """捕获所有显示器并合并

        Returns:
            合并后的图像，失败返回None
        """
        if self.has_mss:
            return self._capture_with_mss()
        else:
            return self._capture_with_pil()

    def _capture_with_mss(self) -> Optional[Image.Image]:
        """使用mss捕获所有显示器"""
        try:
            with self.mss.mss() as sct:
                # 获取所有显示器信息
                monitors = sct.monitors[1:]  # 第一个是虚拟组合显示器，跳过

                if not monitors:
                    self.logger.warning("未检测到显示器")
                    return None

                # 计算合并后的尺寸
                total_width = sum(m["width"] for m in monitors)
                max_height = max(m["height"] for m in monitors)

                # 创建合并图像
                merged = Image.new("RGB", (total_width, max_height))

                # 逐个捕获显示器并合并
                x_offset = 0
                for i, monitor in enumerate(monitors):
                    # 捕获显示器
                    screenshot = sct.grab(monitor)
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

                    # 粘贴到合并图像
                    merged.paste(img, (x_offset, 0))
                    x_offset += monitor["width"]

                    self.logger.debug(
                        f"显示器 {i+1}: {monitor['width']}x{monitor['height']}"
                    )

                self.logger.info(
                    f"✅ 多显示器截图成功: {total_width}x{max_height} ({len(monitors)}个显示器)"
                )
                return merged

        except Exception as e:
            self.logger.error(f"mss截图失败: {e}, 降级到PIL模式")
            return self._capture_with_pil()

    def _capture_with_pil(self) -> Optional[Image.Image]:
        """使用PIL捕获屏幕（降级方案）"""
        try:
            screenshot = ImageGrab.grab(all_screens=True)
            self.logger.info(
                f"✅ PIL截图成功: {screenshot.size[0]}x{screenshot.size[1]}"
            )
            return screenshot
        except Exception as e:
            self.logger.error(f"PIL截图失败: {e}")
            return None


# ========== 感知哈希相似度检测 ==========
class PerceptualHash:
    """感知哈希相似度检测器"""

    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold
        self.has_imagehash = False
        self.logger = logging.getLogger(__name__)
        self.cache = {}  # 哈希缓存
        self.cache_lock = threading.RLock()

        # 尝试导入imagehash
        try:
            import imagehash

            self.imagehash = imagehash
            self.has_imagehash = True
            self.logger.info("✅ 已启用感知哈希相似度检测")
        except ImportError:
            self.logger.warning("⚠️ imagehash未安装，使用MD5检测")

    def are_similar(self, img1_path: str, img2_path: str) -> bool:
        """判断两张图片是否相似

        多层检测策略：
        1. 快速路径：文件大小比较
        2. 标准路径：感知哈希
        3. 降级路径：MD5
        """
        if not os.path.exists(img1_path) or not os.path.exists(img2_path):
            return False

        try:
            # ===== 快速路径：文件大小比较 =====
            size1 = os.path.getsize(img1_path)
            size2 = os.path.getsize(img2_path)

            if abs(size1 - size2) / max(size1, size2) > 0.3:
                return False

            # ===== 标准路径：感知哈希 =====
            if self.has_imagehash:
                similarity = self._compare_with_phash(img1_path, img2_path)
                if similarity is not None:
                    return similarity >= self.threshold

            # ===== 降级路径：MD5 =====
            return self._compare_with_md5(img1_path, img2_path)

        except Exception as e:
            self.logger.debug(f"相似度检测失败: {e}")
            return False

    def _compare_with_phash(self, img1_path: str, img2_path: str) -> Optional[float]:
        """使用感知哈希比较"""
        try:
            # 获取或计算哈希
            hash1 = self._get_phash(img1_path)
            hash2 = self._get_phash(img2_path)

            if hash1 is None or hash2 is None:
                return None

            # 计算汉明距离
            distance = hash1 - hash2

            # 转换为相似度 (0-1)
            similarity = 1 - (distance / 64)  # 64位哈希

            return similarity

        except Exception as e:
            self.logger.debug(f"感知哈希比较失败: {e}")
            return None

    def _get_phash(self, image_path: str):
        """获取图片的感知哈希（带缓存）"""
        with self.cache_lock:
            # 检查缓存
            if image_path in self.cache:
                return self.cache[image_path]

            try:
                # 打开图片并转换为灰度图
                img = Image.open(image_path).convert("L")

                # 调整大小
                img = img.resize((64, 64), Image.Resampling.LANCZOS)

                # 计算感知哈希
                phash = self.imagehash.phash(img)

                # 缓存结果
                self.cache[image_path] = phash

                return phash

            except Exception as e:
                self.logger.debug(f"计算感知哈希失败: {e}")
                return None
            finally:
                # 限制缓存大小
                if len(self.cache) > 100:
                    with self.cache_lock:
                        # 删除最旧的50个
                        for key in list(self.cache.keys())[:50]:
                            del self.cache[key]

    def _compare_with_md5(self, img1_path: str, img2_path: str) -> bool:
        """使用MD5比较（降级方案）"""
        try:
            hash1 = hashlib.md5(open(img1_path, "rb").read()).hexdigest()
            hash2 = hashlib.md5(open(img2_path, "rb").read()).hexdigest()
            return hash1 == hash2
        except Exception:
            return False


# ========== 增强的重试装饰器 ==========
def smart_retry(
    max_retries: int = 3,
    base_delay: float = 2,
    max_delay: float = 120,
    jitter: float = 5,
    exceptions: tuple = (Exception,),
    no_retry_status_codes: tuple = (400, 401, 403, 404, 405),
):
    """智能指数退避重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        jitter: 随机抖动（秒）
        exceptions: 需要重试的异常类型
        no_retry_status_codes: 不重试的HTTP状态码
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            logger = logging.getLogger(__name__)

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)

                except requests.exceptions.HTTPError as e:
                    # HTTP错误特殊处理
                    if hasattr(e, "response") and e.response:
                        status_code = e.response.status_code
                        if status_code in no_retry_status_codes:
                            logger.warning(f"HTTP {status_code} 不重试")
                            raise

                    last_exception = e

                except exceptions as e:
                    last_exception = e

                except Exception as e:
                    # 其他异常直接抛出
                    raise e

                # 最后一次尝试失败
                if attempt == max_retries - 1:
                    logger.error(
                        f"函数 {func.__name__} 在 {max_retries} 次尝试后失败: {last_exception}"
                    )
                    raise last_exception

                # 计算延迟时间（指数退避 + 抖动）
                delay = min(base_delay * (2**attempt), max_delay)
                if jitter > 0:
                    delay += random.uniform(0, jitter)

                logger.warning(
                    f"函数 {func.__name__} 执行失败 (尝试 {attempt + 1}/{max_retries}): {last_exception}\n"
                    f"{delay:.1f}秒后重试..."
                )

                time.sleep(delay)

            return None

        return wrapper

    return decorator


# ========== 增强的托盘图标 ==========
class EnhancedTrayIcon(TrayIcon):
    """增强的托盘图标类"""

    def __init__(self, client):
        self.client = client

        # 通知控制
        self.last_notification = {}
        self.notification_cooldown = 60  # 通知冷却时间（秒）

        # 依赖可用性标志
        self.pystray_available = False
        self.plyer_available = False

        # ===== 添加语言检测（必须在super()之前）=====
        self.system_lang = self.detect_language()
        # ======================================

        super().__init__(client)

        # 检查依赖
        try:
            import pystray

            self.pystray = pystray
            self.pystray_available = True
        except ImportError:
            pass

        try:
            from plyer import notification

            self.plyer_notification = notification
            self.plyer_available = True
        except ImportError:
            pass

        self.icon = None

    def detect_language(self):
        """检测系统语言"""
        try:
            import locale

            lang, _ = locale.getdefaultlocale()
            if lang:
                if lang.startswith("zh"):
                    return "zh"
                elif lang.startswith("vi"):
                    return "vi"
                elif lang.startswith("en"):
                    return "en"
        except:
            pass
        return "en"

    def get_text(self, key):
        """获取多语言文本"""
        texts = {
            # 菜单项
            "show_status": {
                "zh": "📊 显示状态",
                "vi": "📊 Hiển thị trạng thái",
                "en": "📊 Show Status",
            },
            "health_status": {
                "zh": "❤️ 健康状态",
                "vi": "❤️ Trạng thái sức khỏe",
                "en": "❤️ Health Status",
            },
            "watchdog_status": {
                "zh": "🐕 看门狗状态",
                "vi": "🐕 Trạng thái Watchdog",
                "en": "🐕 Watchdog Status",
            },
            "pause_monitor": {
                "zh": "⏸️ 暂停监控",
                "vi": "⏸️ Tạm dừng giám sát",
                "en": "⏸️ Pause Monitoring",
            },
            "resume_monitor": {
                "zh": "▶️ 恢复监控",
                "vi": "▶️ Tiếp tục giám sát",
                "en": "▶️ Resume Monitoring",
            },
            "screenshot_now": {
                "zh": "🔄 立即截图",
                "vi": "🔄 Chụp màn hình ngay",
                "en": "🔄 Screenshot Now",
            },
            "upload_queue": {
                "zh": "📦 上传队列",
                "vi": "📦 Hàng đợi tải lên",
                "en": "📦 Upload Queue",
            },
            "cleanup_cache": {
                "zh": "🧹 清理缓存",
                "vi": "🧹 Dọn bộ nhớ đệm",
                "en": "🧹 Cleanup Cache",
            },
            "network_diagnostic": {
                "zh": "🌐 网络诊断",
                "vi": "🌐 Chẩn đoán mạng",
                "en": "🌐 Network Diagnostic",
            },
            "autostart": {
                "zh": "⚡ 开机自启",
                "vi": "⚡ Tự động khởi động",
                "en": "⚡ Auto Start",
            },
            "view_log": {
                "zh": "📝 查看日志",
                "vi": "📝 Xem nhật ký",
                "en": "📝 View Log",
            },
            "exit": {
                "zh": "❌ 退出",
                "vi": "❌ Thoát",
                "en": "❌ Exit",
            },
            # 通知标题
            "notification_monitor": {
                "zh": "监控",
                "vi": "Giám sát",
                "en": "Monitor",
            },
            "notification_health": {
                "zh": "健康监控",
                "vi": "Sức khỏe",
                "en": "Health",
            },
            "notification_watchdog": {
                "zh": "看门狗",
                "vi": "Watchdog",
                "en": "Watchdog",
            },
            "notification_queue": {
                "zh": "上传队列",
                "vi": "Hàng đợi",
                "en": "Queue",
            },
            "notification_screenshot": {
                "zh": "截图",
                "vi": "Chụp màn hình",
                "en": "Screenshot",
            },
            "notification_cache": {
                "zh": "缓存清理",
                "vi": "Dọn cache",
                "en": "Cache",
            },
            "notification_network": {
                "zh": "网络诊断",
                "vi": "Mạng",
                "en": "Network",
            },
            "notification_exit": {
                "zh": "退出",
                "vi": "Thoát",
                "en": "Exit",
            },
            # 通知消息
            "msg_paused": {
                "zh": "监控已暂停",
                "vi": "Đã tạm dừng giám sát",
                "en": "Monitoring Paused",
            },
            "msg_resumed": {
                "zh": "监控已恢复",
                "vi": "Đã tiếp tục giám sát",
                "en": "Monitoring Resumed",
            },
            "msg_screenshot_triggered": {
                "zh": "已触发立即截图",
                "vi": "Đã kích hoạt chụp màn hình",
                "en": "Screenshot Triggered",
            },
            "msg_cache_cleaned": {
                "zh": "缓存清理完成",
                "vi": "Đã dọn bộ nhớ đệm",
                "en": "Cache Cleanup Complete",
            },
            "msg_exiting": {
                "zh": "正在退出程序...",
                "vi": "Đang thoát chương trình...",
                "en": "Exiting...",
            },
            "msg_health_disabled": {
                "zh": "健康监控系统未启用",
                "vi": "Hệ thống sức khỏe chưa được kích hoạt",
                "en": "Health monitoring system not enabled",
            },
            "msg_watchdog_disabled": {
                "zh": "看门狗系统未启用",
                "vi": "Hệ thống Watchdog chưa được kích hoạt",
                "en": "Watchdog system not enabled",
            },
            "msg_queue_disabled": {
                "zh": "上传队列系统未启用",
                "vi": "Hàng đợi tải lên chưa được kích hoạt",
                "en": "Upload queue system not enabled",
            },
            # 状态文本
            "running": {
                "zh": "运行中",
                "vi": "Đang chạy",
                "en": "Running",
            },
            "stopped": {
                "zh": "已停止",
                "vi": "Đã dừng",
                "en": "Stopped",
            },
            "online": {
                "zh": "在线",
                "vi": "Trực tuyến",
                "en": "Online",
            },
            "offline": {
                "zh": "离线",
                "vi": "Ngoại tuyến",
                "en": "Offline",
            },
            "normal": {
                "zh": "正常",
                "vi": "Bình thường",
                "en": "Normal",
            },
            "paused": {
                "zh": "已暂停",
                "vi": "Đã tạm dừng",
                "en": "Paused",
            },
            # 图标标题
            "title_normal": {
                "zh": "员工监控系统 - {}张截图",
                "vi": "Hệ thống giám sát - {} ảnh chụp",
                "en": "Employee Monitor - {} screenshots",
            },
            "title_paused": {
                "zh": "员工监控系统 - 已暂停",
                "vi": "Hệ thống giám sát - Đã tạm dừng",
                "en": "Employee Monitor - Paused",
            },
            "title_offline": {
                "zh": "员工监控系统 - 离线模式",
                "vi": "Hệ thống giám sát - Chế độ ngoại tuyến",
                "en": "Employee Monitor - Offline Mode",
            },
            "degraded": {"zh": "降级", "vi": "Suy giảm", "en": "Degraded"},
            "unhealthy": {"zh": "异常", "vi": "Bất thường", "en": "Unhealthy"},
            "unknown": {"zh": "未知", "vi": "Không xác định", "en": "Unknown"},
            "health_rate": {
                "zh": "健康率",
                "vi": "Tỷ lệ sức khỏe",
                "en": "Health Rate",
            },
            "total_recoveries": {
                "zh": "总恢复次数",
                "vi": "Tổng số lần phục hồi",
                "en": "Total Recoveries",
            },
            "component_details": {
                "zh": "组件详情",
                "vi": "Chi tiết thành phần",
                "en": "Component Details",
            },
            "failures": {"zh": "失败", "vi": "Thất bại", "en": "Failures"},
            "total_restarts": {
                "zh": "总重启次数",
                "vi": "Tổng số lần khởi động lại",
                "en": "Total Restarts",
            },
            "failed_restarts": {
                "zh": "失败重启",
                "vi": "Khởi động lại thất bại",
                "en": "Failed Restarts",
            },
            "monitored_processes": {
                "zh": "监控进程",
                "vi": "Tiến trình được giám sát",
                "en": "Monitored Processes",
            },
            "restarts": {"zh": "重启", "vi": "Khởi động lại", "en": "Restarts"},
            "queue_size": {
                "zh": "队列大小",
                "vi": "Kích thước hàng đợi",
                "en": "Queue Size",
            },
            "processed": {"zh": "已处理", "vi": "Đã xử lý", "en": "Processed"},
            "failed": {"zh": "失败", "vi": "Thất bại", "en": "Failed"},
            "retried": {"zh": "重试", "vi": "Thử lại", "en": "Retried"},
            "discarded": {"zh": "丢弃", "vi": "Đã hủy", "en": "Discarded"},
            "cache_files": {"zh": "缓存文件", "vi": "Tệp cache", "en": "Cache Files"},
            "cache_size": {
                "zh": "缓存大小",
                "vi": "Kích thước cache",
                "en": "Cache Size",
            },
            "current_server": {
                "zh": "当前服务器",
                "vi": "Máy chủ hiện tại",
                "en": "Current Server",
            },
            "online_mode": {
                "zh": "在线模式",
                "vi": "Chế độ trực tuyến",
                "en": "Online Mode",
            },
            "heartbeat": {"zh": "心跳", "vi": "Heartbeat", "en": "Heartbeat"},
            "enabled": {"zh": "已启用", "vi": "Đã bật", "en": "Enabled"},
            "disabled": {"zh": "已禁用", "vi": "Đã tắt", "en": "Disabled"},
            "server_ok": {
                "zh": "服务器连接正常",
                "vi": "Kết nối máy chủ bình thường",
                "en": "Server Connection OK",
            },
            "latency": {"zh": "延迟", "vi": "Độ trễ", "en": "Latency"},
            "server_status": {
                "zh": "服务器状态码",
                "vi": "Mã trạng thái máy chủ",
                "en": "Server Status Code",
            },
            "connection_failed": {
                "zh": "连接失败",
                "vi": "Kết nối thất bại",
                "en": "Connection Failed",
            },
        }
        return texts.get(key, {}).get(self.system_lang, texts[key]["en"])

    def create_icon(self):
        """创建增强的托盘图标"""
        if not self.pystray_available:
            return

        # 导入需要的模块
        from PIL import Image, ImageDraw

        # 创建图标图像
        image = self._create_icon_image()

        # 创建增强菜单（使用多语言）
        menu = (
            self.pystray.MenuItem(self.get_text("show_status"), self.show_status),
            self.pystray.MenuItem(
                self.get_text("health_status"), self.show_health_status
            ),
            self.pystray.MenuItem(
                self.get_text("watchdog_status"), self.show_watchdog_status
            ),
            self.pystray.Menu.SEPARATOR,
            self.pystray.MenuItem(
                self.get_text("pause_monitor"),
                self.pause_monitor,
                enabled=lambda item: not self.client.paused,
            ),
            self.pystray.MenuItem(
                self.get_text("resume_monitor"),
                self.resume_monitor,
                enabled=lambda item: self.client.paused,
            ),
            self.pystray.MenuItem(
                self.get_text("screenshot_now"), self.take_screenshot_now
            ),
            self.pystray.Menu.SEPARATOR,
            self.pystray.MenuItem(
                self.get_text("upload_queue"), self.show_queue_status
            ),
            self.pystray.MenuItem(self.get_text("cleanup_cache"), self.cleanup_cache),
            self.pystray.MenuItem(
                self.get_text("network_diagnostic"), self.network_diagnostic
            ),
            self.pystray.Menu.SEPARATOR,
            self.pystray.MenuItem(
                self.get_text("autostart"),
                self.toggle_autostart,
                checked=lambda item: self.is_autostart_enabled(),
            ),
            self.pystray.MenuItem(self.get_text("view_log"), self.open_log),
            self.pystray.Menu.SEPARATOR,
            self.pystray.MenuItem(self.get_text("exit"), self.exit_app),
        )

        self.icon = self.pystray.Icon("employee_monitor", image, "员工监控系统", menu)

    def _create_icon_image(self):
        """创建图标图像（带状态指示）"""
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (64, 64), color=(102, 126, 234))
        draw = ImageDraw.Draw(image)

        # 绘制相机图标
        draw.rectangle([16, 20, 48, 44], outline=(255, 255, 255), width=2)
        draw.ellipse([28, 28, 36, 36], fill=(255, 255, 255))
        draw.line([40, 28, 44, 24], fill=(255, 255, 255), width=2)

        # 根据状态添加小圆点
        if self.client.paused:
            # 暂停状态 - 黄色圆点
            draw.ellipse([48, 8, 56, 16], fill=(255, 255, 0), outline=(0, 0, 0))
        elif self.client.offline_mode:
            # 离线状态 - 红色圆点
            draw.ellipse([48, 8, 56, 16], fill=(255, 0, 0), outline=(0, 0, 0))
        else:
            # 正常状态 - 绿色圆点
            draw.ellipse([48, 8, 56, 16], fill=(0, 255, 0), outline=(0, 0, 0))

        return image

    def show_status(self):
        """显示基本状态（继承自父类）"""
        super().show_status()

    def show_health_status(self):
        """显示健康状态"""
        if not hasattr(self.client, "health_monitor"):
            self._show_notification(
                self.get_text("notification_health"),
                self.get_text("msg_health_disabled"),
            )
            return

        summary = self.client.health_monitor.get_summary()
        components = self.client.health_monitor.get_all_status()

        message = f"{self.get_text('health_status')}:\n"
        message += f"{self.get_text('normal')}: {summary['healthy']}, {self.get_text('degraded')}: {summary['degraded']}\n"
        message += f"{self.get_text('unhealthy')}: {summary['unhealthy']}, {self.get_text('unknown')}: {summary['unknown']}\n"
        message += (
            f"{self.get_text('health_rate')}: {summary['health_rate']*100:.1f}%\n"
        )
        message += (
            f"{self.get_text('total_recoveries')}: {summary['total_recoveries']}\n\n"
        )
        message += f"{self.get_text('component_details')}:\n"

        for name, comp in list(components.items())[:5]:
            message += f"{name}: {comp.status.value}"
            if comp.failure_count > 0:
                message += f" ({self.get_text('failures')}:{comp.failure_count})"
            message += "\n"

        self._show_notification(self.get_text("notification_health"), message)

    def show_watchdog_status(self):
        """显示看门狗状态"""
        if not hasattr(self.client, "watchdog"):
            self._show_notification(
                self.get_text("notification_watchdog"),
                self.get_text("msg_watchdog_disabled"),
            )
            return

        status = self.client.watchdog.get_status()

        message = f"{self.get_text('watchdog_status')}:\n"
        message += f"{self.get_text('running') if status['running'] else self.get_text('stopped')}\n"
        message += (
            f"{self.get_text('total_restarts')}: {status['stats']['total_restarts']}\n"
        )
        message += f"{self.get_text('failed_restarts')}: {status['stats']['failed_restarts']}\n\n"
        message += f"{self.get_text('monitored_processes')}:\n"

        for name, proc in status["processes"].items():
            status_icon = "✅" if proc["alive"] else "❌"
            message += f"{status_icon} {name}: {proc['status']}"
            if proc["restart_count"] > 0:
                message += f" ({self.get_text('restarts')}:{proc['restart_count']})"
            message += "\n"

        self._show_notification(self.get_text("notification_watchdog"), message)

    def show_queue_status(self):
        """显示上传队列状态"""
        if not hasattr(self.client, "upload_queue"):
            self._show_notification(
                self.get_text("notification_queue"), self.get_text("msg_queue_disabled")
            )
            return

        stats = self.client.upload_queue.get_stats()
        queue_percent = (stats["queue_size"] / stats["queue_maxsize"]) * 100

        message = f"{self.get_text('queue_size')}: {stats['queue_size']}/{stats['queue_maxsize']} ({queue_percent:.1f}%)\n"
        message += f"{self.get_text('processed')}: {stats['processed']}, {self.get_text('failed')}: {stats['failed']}\n"
        message += f"{self.get_text('retried')}: {stats['retried']}, {self.get_text('discarded')}: {stats['discarded']}\n"
        message += f"{self.get_text('cache_files')}: {stats['cache_count']}, {self.get_text('cache_size')}: {stats['cache_size']/1024/1024:.1f}MB"

        self._show_notification(self.get_text("notification_queue"), message)

    def pause_monitor(self):
        """暂停监控"""
        self.client.paused = True
        self._show_notification(
            self.get_text("notification_monitor"), self.get_text("msg_paused")
        )
        self.update_icon_title()

    def resume_monitor(self):
        """恢复监控"""
        self.client.paused = False
        self._show_notification(
            self.get_text("notification_monitor"), self.get_text("msg_resumed")
        )
        self.update_icon_title()

    def take_screenshot_now(self):
        """立即截图"""
        self.client.take_screenshot_now = True
        self._show_notification(
            self.get_text("notification_screenshot"),
            self.get_text("msg_screenshot_triggered"),
        )

    def cleanup_cache(self):
        """手动清理缓存"""
        if not hasattr(self.client, "upload_queue"):
            return

        self.client.upload_queue._cleanup_cache()
        self._show_notification(
            self.get_text("notification_cache"), self.get_text("msg_cache_cleaned")
        )

    def network_diagnostic(self):
        """网络诊断"""
        message = f"{self.get_text('current_server')}: {self.client.current_server}\n"
        message += f"Client ID: {self.client.client_id}\n"
        message += f"{self.get_text('online_mode')}: {self.get_text('online') if not self.client.offline_mode else self.get_text('offline')}\n"
        message += f"{self.get_text('heartbeat')}: {self.get_text('enabled') if self.client.enable_heartbeat else self.get_text('disabled')}\n\n"

        # 测试连接
        try:
            import requests

            start = time.time()
            response = requests.get(
                f"{self.client.current_server}/health", timeout=5, verify=False
            )
            elapsed = (time.time() - start) * 1000

            if response.status_code == 200:
                message += f"✅ {self.get_text('server_ok')} ({self.get_text('latency')}: {elapsed:.0f}ms)"
            else:
                message += f"⚠️ {self.get_text('server_status')}: {response.status_code}"
        except Exception as e:
            message += f"❌ {self.get_text('connection_failed')}: {e}"

        self._show_notification(self.get_text("notification_network"), message)

    def toggle_autostart(self):
        """切换开机自启"""
        super().toggle_autostart()

    def is_autostart_enabled(self):
        """检查开机自启是否启用"""
        return super().is_autostart_enabled()

    def open_log(self):
        """打开日志文件"""
        super().open_log()

    def exit_app(self):
        """退出程序"""
        self._show_notification(
            self.get_text("notification_exit"), self.get_text("msg_exiting")
        )
        self.client.stop()
        if self.icon:
            self.icon.stop()

    def _show_notification(self, title: str, message: str):
        """显示通知（带冷却控制）"""
        now = time.time()
        key = f"{title}_{message[:50]}"

        # 检查冷却时间
        if key in self.last_notification:
            if now - self.last_notification[key] < self.notification_cooldown:
                return

        self.last_notification[key] = now

        if self.plyer_available:
            try:
                self.plyer_notification.notify(
                    title=f"员工监控系统 - {title}", message=message, timeout=5
                )
            except Exception as e:
                print(f"{title}: {message} (通知失败: {e})")
        else:
            print(f"{title}: {message}")

    def update_icon_title(self):
        """更新图标标题（显示当前状态）"""
        if self.icon:
            if self.client.paused:
                self.icon.title = self.get_text("title_paused")
            elif self.client.offline_mode:
                self.icon.title = self.get_text("title_offline")
            else:
                stats = self.client.get_stats()
                self.icon.title = self.get_text("title_normal").format(
                    stats.get("screenshots_taken", 0)
                )

    def run(self):
        """运行托盘图标"""
        if not self.pystray_available:
            print("⚠️ pystray未安装，托盘图标功能不可用")
            return

        self.create_icon()
        if self.icon:
            self.icon.run()


# ========== 增强的配置管理器 ==========
class EnhancedConfigManager(ConfigManager):
    """增强的配置管理器（支持版本升级和备份）"""

    CONFIG_VERSION = "3.2.0"  # 版本升级

    def __init__(self, config_file="config.json"):
        self.logger = logging.getLogger(__name__)
        self.backup_dir = Path("backup")
        self.backup_dir.mkdir(exist_ok=True)

        super().__init__(config_file)

        # 配置变更回调
        self.change_callbacks = []

    def load(self):
        """加载配置文件（带版本检测和自动升级）"""
        with self.lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        loaded_config = json.load(f)

                    # 版本检测
                    old_version = loaded_config.get("version")

                    if not old_version or old_version != self.CONFIG_VERSION:
                        self._upgrade_config(loaded_config, old_version)
                    else:
                        self.config.update(loaded_config)

                    self.last_mtime = os.path.getmtime(self.config_file)

                    # 验证配置
                    self._validate_config()

                    return True

                except Exception as e:
                    self.logger.error(f"加载配置文件失败: {e}")
                    self._backup_and_reset()

            # 创建默认配置
            self.save()
            return False

    def _upgrade_config(self, old_config: dict, old_version: str):
        """升级配置"""
        self.logger.info(
            f"🔄 检测到配置版本变更: {old_version or '无'} -> {self.CONFIG_VERSION}"
        )

        # 备份旧配置
        backup_file = self._backup_config()

        # 合并配置
        new_config = self.DEFAULT_CONFIG.copy()
        for key, value in old_config.items():
            # 忽略废弃的字段
            if key in new_config and key != "version":
                new_config[key] = value

        # 记录升级信息
        new_config["upgrade_history"] = new_config.get("upgrade_history", [])
        new_config["upgrade_history"].append(
            {
                "time": datetime.now().isoformat(),
                "from": old_version or "unknown",
                "to": self.CONFIG_VERSION,
                "backup": str(backup_file),
            }
        )

        self.config = new_config
        self.logger.info(f"✅ 配置升级完成，备份已保存: {backup_file}")

    def _backup_config(self) -> Path:
        """备份当前配置"""
        if not os.path.exists(self.config_file):
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"config_backup_{timestamp}.json"

        try:
            import shutil

            shutil.copy2(self.config_file, backup_file)

            # 清理旧备份（保留30天）
            self._cleanup_old_backups()

            return backup_file

        except Exception as e:
            self.logger.error(f"备份配置失败: {e}")
            return None

    def _cleanup_old_backups(self, days: int = 30):
        """清理旧备份"""
        try:
            cutoff = time.time() - days * 24 * 3600
            for backup in self.backup_dir.glob("config_backup_*.json"):
                if backup.stat().st_mtime < cutoff:
                    backup.unlink()
                    self.logger.debug(f"删除旧备份: {backup}")
        except Exception as e:
            self.logger.error(f"清理旧备份失败: {e}")

    def _backup_and_reset(self):
        """备份后重置配置"""
        self._backup_config()
        self.config = self.DEFAULT_CONFIG.copy()
        self.save()
        self.logger.warning("⚠️ 配置文件损坏，已重置为默认配置")

    def _validate_config(self):
        """验证配置有效性"""
        changed = False

        # 验证服务器URL
        if not self.config.get("server_urls"):
            self.config["server_urls"] = self.DEFAULT_CONFIG["server_urls"]
            changed = True

        # 验证间隔
        interval = self.config.get("interval")
        if interval is None or interval < 10 or interval > 3600:
            self.config["interval"] = self.DEFAULT_CONFIG["interval"]
            changed = True

        # 验证质量
        quality = self.config.get("quality")
        if quality is None or quality < 10 or quality > 100:
            self.config["quality"] = self.DEFAULT_CONFIG["quality"]
            changed = True

        # 验证格式
        format_val = self.config.get("format")
        if format_val not in ["webp", "jpg", "jpeg"]:
            self.config["format"] = self.DEFAULT_CONFIG["format"]
            changed = True

        if changed:
            self.save()
            self.logger.info("✅ 配置验证完成，已修复无效值")

    def register_change_callback(self, callback: callable):
        """注册配置变更回调"""
        self.change_callbacks.append(callback)

    def set(self, key, value):
        """设置配置项（触发回调）"""
        old_value = self.config.get(key)
        super().set(key, value)

        if old_value != value:
            for callback in self.change_callbacks:
                try:
                    callback(key, old_value, value)
                except Exception as e:
                    self.logger.error(f"配置变更回调执行失败: {e}")


# ========== 增强的MonitorClient类 ==========
class MonitorClient:
    """监控客户端主类（增强版）"""

    def __init__(self, config_file="config.json", force_reconfigure=False):
        # 使用增强的配置管理器
        self.config_manager = EnhancedConfigManager(config_file)
        self.system_info = SystemInfoCollector()
        self.api_client = None

        self.CURRENT_VERSION = "3.2.0"  # 版本升级
        self._check_and_reset_old_config()

        self.force_network_check = False
        self.first_run = False
        self._force_reconfigure = force_reconfigure

        # ========== 先定义 logger ==========
        self.logger = logging.getLogger(__name__)
        # =================================

        self._load_config()
        self._check_first_run()

        # 检查是否首次运行
        if not self.client_id:
            self.first_run = True
            self.logger.info("🔔 检测到首次运行，将启动设置向导")

        # 初始化各系统
        self._init_health_monitor()
        self._init_upload_queue()
        self._init_screenshot_manager()
        self._init_multi_monitor()
        self._init_phash_detector()
        self._init_process_watchdog()

        # 状态变量
        self.running = False
        self.paused = False
        self.take_screenshot_now = False
        self.offline_mode = False
        self.current_server_index = 0

        # 统计信息
        self.stats = {
            "screenshots_taken": 0,
            "screenshots_uploaded": 0,
            "upload_failures": 0,
            "skipped_similar": 0,
            "start_time": None,
            "last_upload_time": None,
            "last_heartbeat": None,
            "errors": [],
        }

        # 线程锁
        self.stats_lock = threading.RLock()
        self.error_lock = threading.RLock()

        # 尝试创建增强的托盘图标
        try:
            self.tray = EnhancedTrayIcon(self)
            self.logger.info("✅ 增强托盘图标已创建")
        except ImportError:
            self.logger.warning("⚠️ pystray未安装，托盘图标功能不可用")
            self.tray = None
        except Exception as e:
            self.logger.error(f"❌ 创建托盘图标失败: {e}")
            self.tray = None

        # 注册配置变更回调
        self.config_manager.register_change_callback(self._on_config_changed)

    # ========== 初始化相关方法 ==========
    def _load_config(self):
        """从配置管理器加载设置"""
        from client_config import Config as ClientConfig

        self.client_id = self.config_manager.get("client_id")
        self.employee_id = self.config_manager.get("employee_id")

        # 服务器地址：使用配置文件
        self.server_urls = ClientConfig.DEFAULT_SERVERS
        self.config_manager.set("server_urls", self.server_urls)
        self.current_server = self.server_urls[0] if self.server_urls else None

        # 初始化配置，但之后会被服务器覆盖
        self.interval = self.config_manager.get(
            "interval", ClientConfig.SCREENSHOT_INTERVAL
        )
        self.quality = self.config_manager.get(
            "quality", ClientConfig.SCREENSHOT_QUALITY
        )
        self.format = self.config_manager.get("format", ClientConfig.SCREENSHOT_FORMAT)

        # 其他配置
        self.auto_start = self.config_manager.get("auto_start", True)
        self.hide_window = self.config_manager.get("hide_window", True)
        self.enable_heartbeat = self.config_manager.get("enable_heartbeat", True)
        self.enable_batch_upload = self.config_manager.get("enable_batch_upload", True)
        self.max_history = self.config_manager.get(
            "max_history", ClientConfig.MAX_HISTORY
        )
        self.similarity_threshold = self.config_manager.get(
            "similarity_threshold", ClientConfig.SIMILARITY_THRESHOLD
        )
        self.retry_times = self.config_manager.get(
            "retry_times", ClientConfig.RETRY_TIMES
        )
        self.retry_delay = self.config_manager.get(
            "retry_delay", ClientConfig.RETRY_DELAY
        )
        self.encryption_enabled = self.config_manager.get("encryption_enabled", False)

        self.logger.info(
            f"📝 初始配置 - 间隔: {self.interval}秒, 质量: {self.quality}, 格式: {self.format}"
        )

    def _check_first_run(self):
        """增强的首次运行检测"""
        # 情况1：强制重新配置标志
        if self._force_reconfigure:
            self.first_run = True
            self.logger.info("🔄 强制重新配置模式")
            return True

        # 情况2：检查配置文件是否存在
        if not os.path.exists(self.config_manager.config_file):
            self.first_run = True
            self.logger.info("🔔 首次运行：没有配置文件")
            return True

        # 情况3：检查必要配置项
        if not self.client_id or not self.employee_id:
            self.first_run = True
            self.logger.info("🔔 首次运行：缺少client_id或employee_id")
            return True

        # 情况4：检查姓名是否为空
        if not self.config_manager.get("employee_name"):
            self.first_run = True
            self.logger.info("🔔 首次运行：员工姓名为空")
            return True

        # 情况5：可选：检查服务器端client_id是否有效
        if self.api_client and self.client_id:
            try:
                response = self.api_client.get(
                    f"/api/client/{self.client_id}/check", timeout=2
                )
                if response and response.get("status") == "invalid":
                    self.first_run = True
                    self.logger.info("🔔 首次运行：client_id在服务器端无效")
                    return True
            except:
                # 网络错误时不视为首次运行
                pass

        self.first_run = False
        return False

    def _check_and_reset_old_config(self):
        """检查是否需要重置旧配置"""
        try:
            config_file = Path("config.json")
            if not config_file.exists():
                return

            with open(config_file, "r", encoding="utf-8") as f:
                old_config = json.load(f)

            old_version = old_config.get("version")
            need_reset = False
            reset_reason = []

            if not old_version:
                need_reset = True
                reset_reason.append("配置版本过旧")
            elif old_version != self.CURRENT_VERSION:
                need_reset = True
                reset_reason.append(
                    f"版本升级: {old_version} -> {self.CURRENT_VERSION}"
                )

            if not need_reset and old_config.get("client_id"):
                try:
                    server_url = old_config.get(
                        "server_urls", ["http://localhost:8000"]
                    )[0]
                    response = requests.get(
                        f"{server_url}/api/client/{old_config['client_id']}/config",
                        timeout=3,
                        verify=False,
                    )
                    if response.status_code == 404:
                        need_reset = True
                        reset_reason.append("服务器端client_id已失效")
                except:
                    pass

            if need_reset:
                self.logger.warning(f"🔄 检测到需要重置配置: {', '.join(reset_reason)}")

                backup_dir = Path("backup")
                backup_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = backup_dir / f"config_backup_{timestamp}.json"

                import shutil

                shutil.copy2(config_file, backup_file)
                self.logger.info(f"📦 旧配置已备份到: {backup_file}")

                config_file.unlink()
                self.logger.info("🗑️ 旧配置已删除")

                self.config_manager.config = self.config_manager.DEFAULT_CONFIG.copy()
                self.config_manager.save()

                self.logger.info("✅ 配置重置完成，将使用新配置")

        except Exception as e:
            self.logger.error(f"检查旧配置时出错: {e}")

    # ========== 验证相关方法 ==========
    def validate_config(self):
        """验证客户端配置有效性"""
        if not self.server_urls:
            self.logger.error("未配置服务器地址")
            return False

        valid_urls = []
        for url in self.server_urls:
            if url.startswith(("http://", "https://")):
                valid_urls.append(url)
            else:
                self.logger.warning(f"无效的服务器URL: {url}")

        if not valid_urls:
            self.logger.error("没有有效的服务器地址")
            return False

        self.server_urls = valid_urls
        self.current_server = valid_urls[0]

        if self.interval < 10 or self.interval > 3600:
            self.logger.warning(f"截图间隔{self.interval}秒不合理，调整为60秒")
            self.interval = 60

        if self.quality < 10 or self.quality > 100:
            self.logger.warning(f"图片质量{self.quality}不合理，调整为80")
            self.quality = 80

        if self.format not in ["webp", "jpg", "jpeg"]:
            self.logger.warning(f"图片格式{self.format}不合理，使用webp")
            self.format = "webp"

        return True

    def detect_best_server(self):
        """检测最佳服务器地址"""
        local_server = "https://one68-2ykz.onrender.com"
        self.logger.info(f"🔧 使用服务器: {local_server}")

        try:
            import requests

            response = requests.get(f"{local_server}/health", timeout=2, verify=False)
            if response.status_code == 200:
                self.logger.info(f"✅ 服务器连接成功")
            else:
                self.logger.warning(f"⚠️ 服务器返回状态码: {response.status_code}")
        except Exception as e:
            self.logger.error(f"❌ 无法连接到服务器 {local_server}: {e}")
            self.logger.error("请确认服务器是否在运行")

        return local_server

    # ========== 注册相关方法 ==========
    def register_with_server(self, silent_mode: bool = False):
        """向服务器注册"""
        self.current_server = self.detect_best_server()

        self.api_client = APIClient(
            self.current_server,
            retry_times=self.retry_times,
            retry_delay=self.retry_delay,
        )

        # ===== 修改：获取员工姓名（增强版）=====
        employee_name = None

        # 情况1：如果是首次运行且不是静默模式，弹出GUI
        if self.first_run and not silent_mode:
            try:
                from client_gui import get_employee_name_gui

                gui_name = get_employee_name_gui()
                if gui_name:
                    employee_name = gui_name
                    self.logger.info(f"✅ 通过GUI获取员工姓名: {employee_name}")
            except Exception as e:
                self.logger.error(f"GUI启动失败: {e}")

        # 情况2：如果没有通过GUI获取到，尝试从配置读取
        if not employee_name:
            saved_name = self.config_manager.get("employee_name")
            if saved_name:
                employee_name = saved_name
                self.logger.info(f"📝 从配置读取员工姓名: {employee_name}")

        # 情况3：如果还是没有，使用Windows用户名
        if not employee_name:
            employee_name = self.system_info.get_windows_user() or "Employee"
            self.logger.info(f"💻 使用系统用户名: {employee_name}")

        # 情况4：如果是强制重新配置模式，确保使用新姓名
        if hasattr(self, "_force_reconfigure") and self._force_reconfigure:
            self.logger.info("🔄 强制重新配置模式，将使用新姓名")
            # 如果已经有姓名，但用户想要重新输入，再次弹出GUI
            if not silent_mode:
                try:
                    from client_gui import get_employee_name_gui

                    gui_name = get_employee_name_gui()
                    if gui_name:
                        employee_name = gui_name
                        self.logger.info(f"✅ 重新配置获取新姓名: {employee_name}")
                except Exception as e:
                    self.logger.error(f"重新配置GUI启动失败: {e}")
        # =====================================

        # 如果已有client_id，获取服务器配置
        if self.client_id:
            self.logger.info(f"使用现有client_id: {self.client_id}")
            try:
                config = self.api_client.get(f"/api/client/{self.client_id}/config")
                if config:
                    self._update_config_from_server(config)
                    self.logger.info(f"✅ 从服务器获取配置成功")
            except Exception as e:
                self.logger.debug(f"获取服务器配置失败: {e}")

        # 获取系统信息
        system_info = self.system_info.get_system_info()

        # 构建注册数据
        register_data = {
            "client_id": self.client_id or None,
            "computer_name": system_info.get("computer_name"),
            "windows_user": system_info.get("windows_user"),
            "mac_address": system_info.get("mac_address"),
            "ip_address": system_info.get("ip_address"),
            "os_version": system_info.get("os_version"),
            "cpu_id": system_info.get("cpu_id"),
            "disk_serial": system_info.get("disk_serial"),
            "client_version": self.CURRENT_VERSION,
            "interval": self.interval,
            "quality": self.quality,
            "format": self.format,
            "employee_name": employee_name,  # 使用处理后的姓名
            "capabilities": ["webp", "heartbeat", "batch", "encryption"],
        }

        # 移除None值
        register_data = {k: v for k, v in register_data.items() if v is not None}

        self.logger.info(f"正在向服务器注册: {self.current_server}")
        self.logger.info(
            f"注册数据: {json.dumps(register_data, indent=2, ensure_ascii=False)}"
        )

        try:
            data = self.api_client.post("/api/client/register", json=register_data)

            self.client_id = data.get("client_id")
            self.employee_id = data.get("employee_id")

            if "config" in data:
                self._update_config_from_server(data["config"])

            self.logger.info(
                f"✅ 注册成功! 客户端ID: {self.client_id}, 员工ID: {self.employee_id}"
            )

            # 保存配置
            self.config_manager.update(
                client_id=self.client_id,
                employee_id=self.employee_id,
                interval=self.interval,
                quality=self.quality,
                format=self.format,
                employee_name=employee_name,  # 保存姓名
                version=self.CURRENT_VERSION,
            )

            # ===== 新增：重置强制重新配置标志 =====
            if hasattr(self, "_force_reconfigure"):
                self._force_reconfigure = False
            # ====================================

            if hasattr(self, "watchdog"):
                self.watchdog.heartbeat("main")

            return True

        except Exception as e:
            self.logger.error(f"注册失败: {e}")
            self.offline_mode = True
            return False

    def _update_config_from_server(self, config):
        """从服务器更新配置"""
        changed = False

        if config.get("interval") and config["interval"] != self.interval:
            old_interval = self.interval
            self.interval = config["interval"]
            changed = True
            self.logger.info(
                f"【服务器强制】截图间隔更新: {old_interval}秒 -> {self.interval}秒"
            )

        if config.get("quality") and config["quality"] != self.quality:
            old_quality = self.quality
            self.quality = config["quality"]
            if self.screenshot_manager:
                self.screenshot_manager.quality = self.quality
            changed = True
            self.logger.info(
                f"【服务器强制】图片质量更新: {old_quality} -> {self.quality}"
            )

        if config.get("format") and config["format"] != self.format:
            old_format = self.format
            self.format = config["format"]
            if self.screenshot_manager:
                self.screenshot_manager.format = self.format
            changed = True
            self.logger.info(
                f"【服务器强制】图片格式更新: {old_format} -> {self.format}"
            )

        if config.get("enable_heartbeat") is not None:
            old_value = self.enable_heartbeat
            self.enable_heartbeat = config["enable_heartbeat"]
            changed = True
            self.logger.info(
                f"【服务器强制】心跳配置更新: {old_value} -> {self.enable_heartbeat}"
            )

        if config.get("enable_batch_upload") is not None:
            old_value = self.enable_batch_upload
            self.enable_batch_upload = config["enable_batch_upload"]
            changed = True
            self.logger.info(
                f"【服务器强制】批量上传配置更新: {old_value} -> {self.enable_batch_upload}"
            )

        if config.get("similarity_threshold") is not None:
            old_value = self.similarity_threshold
            self.similarity_threshold = config["similarity_threshold"]
            if self.phash_detector:
                self.phash_detector.threshold = self.similarity_threshold
            changed = True
            self.logger.info(
                f"【服务器强制】相似度阈值更新: {old_value} -> {self.similarity_threshold}"
            )

        if config.get("retry_times") is not None:
            old_value = self.retry_times
            self.retry_times = config["retry_times"]
            changed = True
            self.logger.info(
                f"【服务器强制】重试次数更新: {old_value} -> {self.retry_times}"
            )

        if changed:
            self.config_manager.update(
                interval=self.interval,
                quality=self.quality,
                format=self.format,
                enable_heartbeat=self.enable_heartbeat,
                enable_batch_upload=self.enable_batch_upload,
                similarity_threshold=self.similarity_threshold,
                retry_times=self.retry_times,
            )

            if hasattr(self, "watchdog"):
                self.watchdog.heartbeat("config")

    # ========== 初始化各系统 ==========
    def _init_health_monitor(self):
        """初始化健康监控系统"""
        self.health_monitor = HealthMonitor(check_interval=60, recovery_cooldown=300)

        # 注册所有组件
        self.health_monitor.register_component("screenshot", self._recover_screenshot)
        self.health_monitor.register_component("upload", self._recover_upload)
        self.health_monitor.register_component("network", self._recover_network)
        self.health_monitor.register_component("heartbeat", self._recover_heartbeat)
        self.health_monitor.register_component("config", self._recover_config)
        self.health_monitor.register_component("watchdog", self._recover_watchdog)

        # 初始化所有组件的状态，避免启动时的超时警告
        try:
            now = time.time()
            components = [
                "screenshot",
                "upload",
                "network",
                "heartbeat",
                "config",
                "watchdog",
            ]

            for component_name in components:
                if component_name in self.health_monitor.components:
                    # 更新最后检查时间
                    self.health_monitor.components[component_name].last_check_time = now

                    # 设置初始状态为健康
                    self.health_monitor.update_status(
                        component_name,
                        HealthStatus.HEALTHY,
                        "组件初始化完成",
                        response_time=0.0,
                        metrics={"init_time": now},
                    )

            self.logger.debug(f"已初始化 {len(components)} 个健康监控组件的状态")

        except Exception as e:
            self.logger.warning(f"初始化组件状态时出现警告（可忽略）: {e}")

        self.logger.info("✅ 健康监控系统已初始化")

    def _init_upload_queue(self):
        """初始化上传队列系统"""
        self.upload_queue = UploadQueue(
            client=self,
            max_queue_size=100,
            worker_count=3,
            cache_dir="cache",
            max_cache_size=500 * 1024 * 1024,
        )
        self.logger.info("✅ 上传队列系统已初始化")

    def _init_screenshot_manager(self):
        """初始化截图管理器"""
        self.screenshot_manager = ScreenshotManager(
            quality=self.quality,
            format=self.format,
            max_history=self.max_history,
            similarity_threshold=self.similarity_threshold,
            encryption_key=os.environ.get("ENCRYPTION_KEY"),
        )

    def _init_multi_monitor(self):
        """初始化多显示器截图"""
        self.multi_monitor = MultiMonitorScreenshot()

    def _init_phash_detector(self):
        """初始化感知哈希检测器"""
        self.phash_detector = PerceptualHash(threshold=self.similarity_threshold)

    def _init_process_watchdog(self):
        """初始化进程看门狗"""
        self.watchdog = ProcessWatchdog(check_interval=30, max_restarts=5)

        self.logger.info("✅ 进程看门狗系统已初始化")

    # ========== 恢复回调 ==========
    def _recover_screenshot(self):
        """截图组件恢复回调"""
        self.logger.info("🔄 执行截图组件恢复")
        if self.screenshot_manager:
            self.screenshot_manager.last_screenshot_path = None
        if hasattr(self, "watchdog"):
            self.watchdog.heartbeat("screenshot")

    def _recover_upload(self):
        """上传组件恢复回调"""
        self.logger.info("🔄 执行上传组件恢复")
        if self.upload_queue and not self.offline_mode:
            threading.Thread(
                target=self.upload_queue._load_cached_tasks, daemon=True
            ).start()
        if hasattr(self, "watchdog"):
            self.watchdog.heartbeat("upload")

    def _recover_network(self):
        """网络组件恢复回调"""
        self.logger.info("🔄 执行网络组件恢复")
        self.force_network_check = True
        if hasattr(self, "watchdog"):
            self.watchdog.heartbeat("network")

    def _recover_heartbeat(self):
        """心跳组件恢复回调"""
        self.logger.info("🔄 执行心跳组件恢复")
        if hasattr(self, "watchdog"):
            self.watchdog.heartbeat("heartbeat")

    def _recover_config(self):
        """配置组件恢复回调"""
        self.logger.info("🔄 执行配置组件恢复")
        self.config_manager.reload_if_changed()
        if hasattr(self, "watchdog"):
            self.watchdog.heartbeat("config")

    def _recover_watchdog(self):
        """看门狗组件恢复回调"""
        self.logger.info("🔄 执行看门狗组件恢复")
        if self.watchdog and not self.watchdog.running:
            self.watchdog.start()
        if hasattr(self, "watchdog"):
            self.watchdog.heartbeat("watchdog")

    # ========== 配置变更 ==========
    def _on_config_changed(self, key: str, old_value, new_value):
        """配置变更回调"""
        self.logger.info(f"配置变更: {key} = {old_value} -> {new_value}")

        if hasattr(self, key):
            setattr(self, key, new_value)

        self.health_monitor.update_status(
            "config", HealthStatus.HEALTHY, f"配置已更新: {key}"
        )

        if hasattr(self, "watchdog"):
            self.watchdog.heartbeat("config")

    # ========== 核心功能 ==========
    def _take_and_process_screenshot(self, last_screenshot_path, consecutive_failures):
        """抽取截图处理逻辑为独立方法"""
        temp_filepath = None  # 用于跟踪临时文件
        try:
            screenshot = self.multi_monitor.capture_all_monitors()
            if not screenshot:
                self.logger.error("截图失败")
                return None

            buffer = get_buffer()
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.{self.format}"
                filepath = os.path.join(os.getcwd(), filename)

                # 先保存到临时文件，然后原子重命名
                temp_fd, temp_path = tempfile.mkstemp(
                    suffix=f".{self.format}", prefix=".tmp_screenshot_", dir=os.getcwd()
                )
                os.close(temp_fd)
                temp_filepath = temp_path

                if self.format == "webp":
                    screenshot.save(
                        temp_filepath,
                        "WEBP",
                        quality=self.quality,
                        optimize=True,
                        method=6,
                    )
                else:
                    screenshot.save(
                        temp_filepath, "JPEG", quality=self.quality, optimize=True
                    )

                # 确保文件完全写入磁盘
                try:
                    with open(temp_filepath, "rb") as f:
                        os.fsync(f.fileno())
                except Exception as e:
                    self.logger.debug(f"文件同步失败（可忽略）: {e}")
                    time.sleep(0.1)

                # 原子重命名到目标文件
                shutil.move(temp_filepath, filepath)
                temp_filepath = None  # 重置，因为文件已重命名

                file_size = os.path.getsize(filepath)

                with self.stats_lock:
                    self.stats["screenshots_taken"] += 1

                self.health_monitor.update_status(
                    "screenshot",
                    HealthStatus.HEALTHY,
                    f"截图成功: {file_size/1024:.1f}KB",
                    metrics={"size": file_size, "format": self.format},
                )

            finally:
                put_buffer(buffer)
                # 清理临时文件（如果存在）
                if temp_filepath and os.path.exists(temp_filepath):
                    try:
                        os.unlink(temp_filepath)
                    except:
                        pass

            # 检查相似度
            if last_screenshot_path and os.path.exists(last_screenshot_path):
                try:
                    if self.phash_detector.are_similar(last_screenshot_path, filepath):
                        self.logger.debug("屏幕内容无变化，跳过上传")

                        # 尝试多次删除
                        for attempt in range(3):
                            try:
                                os.unlink(filepath)
                                break
                            except (OSError, PermissionError) as e:
                                if attempt < 2:
                                    time.sleep(0.1 * (attempt + 1))
                                    continue
                                else:
                                    self.logger.warning(f"无法删除文件 {filepath}: {e}")

                        with self.stats_lock:
                            self.stats["skipped_similar"] += 1
                        consecutive_failures = 0
                        return None
                except Exception as e:
                    self.logger.debug(f"相似度检测失败: {e}")

            # 读取文件数据（使用 with 语句确保文件句柄关闭）
            try:
                with open(filepath, "rb") as f:
                    image_data = f.read()
            except Exception as e:
                self.logger.error(f"读取截图文件失败: {e}")
                return None

            encrypted = (
                self.encryption_enabled
                if hasattr(self, "encryption_enabled")
                else False
            )

            task = UploadTask(
                image_data=image_data,
                filename=os.path.basename(filepath),
                employee_id=self.employee_id,
                client_id=self.client_id,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                computer_name=self.system_info.get_computer_name(),
                windows_user=self.system_info.get_windows_user(),
                format=self.format,
                encrypted=encrypted,
            )

            if self.upload_queue.enqueue(task):
                consecutive_failures = 0

                # 任务已入队，删除原始文件
                if os.path.exists(filepath):
                    # 多次尝试删除
                    for attempt in range(3):
                        try:
                            os.unlink(filepath)
                            break
                        except (OSError, PermissionError) as e:
                            if attempt < 2:
                                time.sleep(0.1 * (attempt + 1))
                                continue
                            else:
                                self.logger.warning(
                                    f"文件 {filepath} 仍在使用，将留在磁盘上: {e}"
                                )

                self.health_monitor.update_status(
                    "upload", HealthStatus.HEALTHY, "任务已添加到队列"
                )
                if hasattr(self, "watchdog"):
                    self.watchdog.heartbeat("upload")

                return filepath
            else:
                consecutive_failures += 1
                self.logger.warning(
                    f"队列已满，保存到本地缓存 (连续失败: {consecutive_failures})"
                )

                self.health_monitor.update_status(
                    "upload",
                    (
                        HealthStatus.DEGRADED
                        if consecutive_failures > 2
                        else HealthStatus.HEALTHY
                    ),
                    f"队列已满，本地缓存",
                )

                return filepath

        except Exception as e:
            self.logger.error(f"截图处理过程出错: {e}", exc_info=True)
            self.health_monitor.update_status(
                "screenshot", HealthStatus.UNHEALTHY, str(e)
            )
            if hasattr(self, "watchdog"):
                self.watchdog.report_failure("screenshot", str(e))

            # 清理临时文件
            if temp_filepath and os.path.exists(temp_filepath):
                try:
                    os.unlink(temp_filepath)
                except:
                    pass

            return None

    def send_heartbeat(self):
        """发送心跳 - 增强版"""
        if not self.enable_heartbeat or self.offline_mode:
            return False
        if not self.api_client or not self.client_id:
            return False

        try:
            start_time = time.time()

            stats = self.system_info.get_system_stats()
            queue_stats = (
                self.upload_queue.get_stats() if hasattr(self, "upload_queue") else {}
            )
            health_summary = (
                self.health_monitor.get_summary()
                if hasattr(self, "health_monitor")
                else {}
            )
            watchdog_status = (
                self.watchdog.get_status() if hasattr(self, "watchdog") else {}
            )

            current_time = datetime.now(timezone.utc)

            heartbeat_data = {
                "status": "online",
                "timestamp": current_time.isoformat(),
                "stats": stats,
                "client_stats": self.get_stats(),
                "queue_stats": queue_stats,
                "health_summary": health_summary,
                "watchdog_status": watchdog_status,
                "paused": bool(self.paused),
                "ip_address": self.system_info.get_ip_address(),
            }

            response = self.api_client.post(
                f"/api/client/{self.client_id}/heartbeat", json=heartbeat_data
            )

            response_time = (time.time() - start_time) * 1000

            if response:
                with self.stats_lock:
                    self.stats["last_heartbeat"] = time.time()

                self.health_monitor.update_status(
                    "heartbeat",
                    HealthStatus.HEALTHY,
                    f"延迟: {response_time:.0f}ms",
                    response_time=response_time,
                )

                if hasattr(self, "watchdog"):
                    self.watchdog.heartbeat("heartbeat")

                self.logger.debug(f"✅ 心跳发送成功 ({response_time:.0f}ms)")
                return True
            else:
                self.health_monitor.update_status(
                    "heartbeat", HealthStatus.DEGRADED, "服务器返回空响应"
                )
                return False

        except Exception as e:
            self.logger.debug(f"心跳发送失败: {e}")

            self.health_monitor.update_status(
                "heartbeat", HealthStatus.UNHEALTHY, str(e)
            )

            if hasattr(self, "watchdog"):
                self.watchdog.report_failure("heartbeat", str(e))

            return False

    def upload_screenshot(self, image_path):
        """上传截图（兼容 client.py 接口）"""
        if self.offline_mode:
            self.logger.debug("离线模式，保存截图到本地")
            return False

        if not self.api_client or not self.client_id:
            self.logger.error("API客户端未初始化或无客户端ID")
            return False

        if not os.path.exists(image_path):
            self.logger.error(f"文件不存在: {image_path}")
            return False

        file_size = os.path.getsize(image_path)
        if file_size == 0:
            self.logger.error(f"文件为空: {image_path}")
            return False

        try:
            from datetime import datetime, timezone, timedelta

            beijing_tz = timezone(timedelta(hours=8))
            now_beijing = datetime.now(beijing_tz)
            timestamp = now_beijing.strftime("%Y-%m-%d %H:%M:%S")

            computer_name = self.system_info.get_computer_name() or ""
            windows_user = self.system_info.get_windows_user() or ""
            encrypted_value = bool(self.encryption_enabled)

            with open(image_path, "rb") as f:
                files = {
                    "file": (os.path.basename(image_path), f, f"image/{self.format}")
                }

                data = {
                    "employee_id": str(self.employee_id),
                    "client_id": str(self.client_id) if self.client_id else "",
                    "timestamp": timestamp,
                    "computer_name": computer_name,
                    "windows_user": windows_user,
                    "encrypted": str(encrypted_value).lower(),
                    "format": self.format,
                }

                response = self.api_client.session.post(
                    f"{self.current_server}/api/upload",
                    files=files,
                    data=data,
                    timeout=60,
                    headers={"Accept": "application/json"},
                )

            if response.status_code == 200:
                with self.stats_lock:
                    self.stats["screenshots_uploaded"] += 1
                    self.stats["last_upload_time"] = time.time()

                self.logger.info(f"✅ 截图上传成功: {os.path.basename(image_path)}")

                try:
                    os.remove(image_path)
                except Exception as e:
                    self.logger.warning(f"删除本地文件失败: {e}")

                return True
            else:
                self.logger.warning(f"上传失败: HTTP {response.status_code}")
                with self.stats_lock:
                    self.stats["upload_failures"] += 1
                return False

        except Exception as e:
            self.logger.error(f"上传出错: {e}")
            with self.stats_lock:
                self.stats["upload_failures"] += 1
            return False

    def upload_screenshots_batch(self):
        """批量上传截图"""
        if not self.enable_batch_upload or self.offline_mode:
            return False

        try:
            # 查找待上传的截图
            screenshots = []
            now = time.time()
            pattern = f"screenshot_*.{self.format}"

            for file in Path(".").glob(pattern):
                file_age = now - file.stat().st_mtime
                file_size = file.stat().st_size

                # 文件超过10分钟且小于10MB
                if file_age > 600 and file_size < 10 * 1024 * 1024:
                    if file.name != self.screenshot_manager.last_screenshot_path:
                        screenshots.append(str(file))

            if not screenshots:
                return False

            self.logger.info(f"准备批量上传 {len(screenshots)} 个截图")

            # 创建ZIP文件
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for screenshot in screenshots:
                    with open(screenshot, "rb") as f:
                        zip_file.writestr(os.path.basename(screenshot), f.read())

            # 准备上传数据
            zip_data = zip_buffer.getvalue()
            files = {"batch": ("screenshots.zip", zip_data, "application/zip")}
            data = {
                "client_id": self.client_id,
                "employee_id": self.employee_id,
                "count": len(screenshots),
            }

            # 上传ZIP
            response = self.api_client.session.post(
                f"{self.current_server}/api/upload/batch",
                files=files,
                data=data,
                timeout=120,
            )

            if response.status_code == 200:
                # 上传成功后删除本地文件
                deleted_count = 0
                for screenshot in screenshots:
                    try:
                        os.remove(screenshot)
                        deleted_count += 1
                    except OSError as e:
                        self.logger.warning(f"删除文件失败 {screenshot}: {e}")

                # 更新统计
                with self.stats_lock:
                    self.stats["screenshots_uploaded"] += len(screenshots)
                    self.stats["last_upload_time"] = time.time()

                self.logger.info(
                    f"✅ 批量上传成功: {len(screenshots)}个文件 (删除{deleted_count}个)"
                )
                return True
            else:
                self.logger.warning(f"批量上传失败: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"批量上传失败: {e}")
            return False

    def upload_cached_screenshots(self):
        """上传缓存的截图（网络恢复时调用）"""
        self.logger.info("开始上传缓存的截图...")
        try:
            # 查找所有本地截图
            pattern = f"screenshot_*.{self.format}"
            screenshots = list(Path(".").glob(pattern))

            if not screenshots:
                self.logger.info("没有缓存的截图")
                return

            self.logger.info(f"找到 {len(screenshots)} 个缓存的截图")

            for screenshot in screenshots:
                if not self.running:
                    break
                if self.offline_mode:
                    break
                self.upload_screenshot(str(screenshot))
                time.sleep(1)  # 避免上传过快
        except Exception as e:
            self.logger.error(f"上传缓存截图失败: {e}")

    def batch_uploader(self):
        """批量上传线程"""
        while self.running:
            time.sleep(1800)  # 30分钟
            if self.running and not self.offline_mode:
                try:
                    self.upload_screenshots_batch()
                except Exception as e:
                    self.logger.error(f"批量上传失败: {e}")

    # ========== 工作线程 ==========
    def work_loop(self):
        """主工作循环 - 固定时间点截图 + 防抖"""
        self.logger.info(f"开始监控，员工ID: {self.employee_id}")
        self.logger.info(f"截图间隔: {self.interval}秒")
        self.logger.info(f"图片格式: {self.format}")

        import math

        last_sync = 0
        consecutive_failures = 0
        last_screenshot_path = None
        last_screenshot_time = 0

        now = time.time()
        next_screenshot = math.ceil(now / self.interval) * self.interval
        self.logger.info(
            f"首次截图时间点: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_screenshot))}"
        )

        while self.running:
            try:
                if hasattr(self, "watchdog"):
                    self.watchdog.heartbeat("main")

                if self.paused:
                    time.sleep(5)
                    continue

                now = time.time()

                if self.take_screenshot_now:
                    self.take_screenshot_now = False
                    self.logger.info("执行立即截图")

                    image_path = self._take_and_process_screenshot(
                        last_screenshot_path, consecutive_failures
                    )
                    if image_path:
                        last_screenshot_path = image_path
                        last_screenshot_time = now

                    next_screenshot = math.ceil(now / self.interval) * self.interval

                elif now >= next_screenshot:
                    if now - last_screenshot_time < 2:
                        self.logger.debug(
                            f"截图太频繁（上次截图在{now - last_screenshot_time:.1f}秒前），跳过本次"
                        )
                        next_screenshot = math.ceil(now / self.interval) * self.interval
                        time.sleep(1)
                        continue

                    self.logger.debug(
                        f"到达截图时间点: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}"
                    )

                    image_path = self._take_and_process_screenshot(
                        last_screenshot_path, consecutive_failures
                    )

                    if image_path:
                        last_screenshot_path = image_path
                        last_screenshot_time = now

                    next_screenshot = math.ceil(now / self.interval) * self.interval

                if now - last_sync > 600 and not self.offline_mode:
                    try:
                        config = self.api_client.get(
                            f"/api/client/{self.client_id}/config"
                        )
                        if config:
                            self._update_config_from_server(config)
                            new_interval = config.get("interval")
                            if new_interval and new_interval != self.interval:
                                self.interval = new_interval
                                next_screenshot = (
                                    math.ceil(now / self.interval) * self.interval
                                )
                    except Exception as e:
                        self.logger.debug(f"同步配置失败: {e}")
                    last_sync = now

                time_to_next = next_screenshot - time.time()
                if time_to_next > 5:
                    sleep_time = min(2, time_to_next - 1)
                    time.sleep(sleep_time)
                else:
                    time.sleep(1)

            except Exception as e:
                self.logger.error(f"工作循环出错: {e}")
                self.stats["errors"].append(
                    {"time": datetime.now().isoformat(), "error": str(e)}
                )
                if hasattr(self, "watchdog"):
                    # 修复：检查方法是否存在
                    if hasattr(self.watchdog, "report_failure"):
                        self.watchdog.report_failure("main", str(e))
                    else:
                        # 如果没有report_failure方法，使用heartbeat或直接记录
                        try:
                            self.watchdog.heartbeat("main_error")
                        except:
                            pass
                time.sleep(60)

    def config_watcher(self):
        """配置文件监控线程"""
        while self.running:
            try:
                if self.config_manager.reload_if_changed():
                    old_interval = self.interval
                    self._load_config()
                    if old_interval != self.interval:
                        self.logger.info(f"截图间隔已更新为: {self.interval}秒")

                    if hasattr(self, "watchdog"):
                        self.watchdog.heartbeat("config")

            except Exception as e:
                self.logger.error(f"配置监控出错: {e}")
                if hasattr(self, "watchdog"):
                    self.watchdog.report_failure("config", str(e))

            time.sleep(5)

    def heartbeat_sender(self):
        """心跳发送线程"""
        heartbeat_failures = 0

        while self.running:
            try:
                if not self.offline_mode:
                    success = self.send_heartbeat()

                    if success:
                        if heartbeat_failures > 0:
                            self.logger.info("心跳恢复")
                        heartbeat_failures = 0
                    else:
                        heartbeat_failures += 1

                        if heartbeat_failures == 1:
                            self.logger.warning("⚠️ 心跳发送失败 (第1次)")
                        elif heartbeat_failures == 2:
                            self.logger.warning("⚠️ 心跳发送失败 (第2次)")
                        elif heartbeat_failures >= 3:
                            self.logger.warning("⚠️ 连续3次心跳失败，触发网络检测")
                            self.force_network_check = True
                            heartbeat_failures = 0
                else:
                    heartbeat_failures = 0

            except Exception as e:
                self.logger.debug(f"心跳异常: {e}")
                heartbeat_failures += 1

            for _ in range(60):
                if not self.running:
                    return
                time.sleep(1)

    def network_monitor(self):
        """工业级网络监控线程"""
        consecutive_failures = 0
        current_server_index = 0

        base_interval = 30
        max_interval = 300
        check_interval = base_interval

        session = requests.Session()
        last_check_time = time.time()

        while self.running:
            try:
                if hasattr(self, "watchdog"):
                    self.watchdog.heartbeat("network")

                current_time = time.time()
                force_check = False

                if self.force_network_check:
                    self.logger.info("收到强制网络检测请求")
                    self.force_network_check = False
                    force_check = True
                    check_interval = base_interval

                time_since_last_check = current_time - last_check_time

                if force_check or time_since_last_check >= check_interval:
                    last_check_time = current_time

                    try:
                        response = session.get(
                            f"{self.current_server}/health", timeout=5, verify=False
                        )

                        if response.status_code == 200:
                            if self.offline_mode:
                                self.logger.info("🌐 网络恢复，重新连接服务器")
                                self.offline_mode = False
                                consecutive_failures = 0
                                check_interval = base_interval

                                try:
                                    self.register_with_server()
                                except Exception as e:
                                    self.logger.error(f"重新注册失败: {e}")

                                if self.screenshot_manager:
                                    threading.Thread(
                                        target=self.upload_queue._load_cached_tasks,
                                        daemon=True,
                                    ).start()
                            else:
                                consecutive_failures = 0
                                check_interval = base_interval

                            if hasattr(self, "watchdog"):
                                self.watchdog.heartbeat("network")
                        else:
                            consecutive_failures += 1

                    except requests.RequestException as e:
                        self.logger.debug(f"健康检测失败: {e}")
                        consecutive_failures += 1

                    if consecutive_failures >= 3:
                        self.logger.warning("服务器连接失败，尝试切换服务器")
                        current_server_index = (current_server_index + 1) % len(
                            self.server_urls
                        )
                        new_server = self.server_urls[current_server_index]
                        self.logger.warning(f"切换服务器 → {new_server}")
                        self.current_server = new_server

                        self.api_client = APIClient(
                            self.current_server,
                            retry_times=self.retry_times,
                            retry_delay=self.retry_delay,
                        )

                        consecutive_failures = 0

                        if current_server_index == 0 and not self.offline_mode:
                            self.logger.warning("⚠️ 所有服务器不可用，进入离线模式")
                            self.offline_mode = True

                            if self.config_manager:
                                self.config_manager.save()

                    if consecutive_failures > 0:
                        check_interval = min(check_interval * 2, max_interval)

                    jitter = random.uniform(0, 5)
                    adjusted_interval = check_interval + jitter
                    self.logger.debug(f"下次检测 {adjusted_interval:.1f}s 后")

                for _ in range(1):
                    if not self.running:
                        return
                    time.sleep(1)

            except Exception as e:
                self.logger.error(f"网络监控异常: {e}")
                if hasattr(self, "watchdog"):
                    self.watchdog.report_failure("network", str(e))
                time.sleep(30)

    # ========== 生命周期 ==========
    def start(self, silent_mode=False):
        """启动监控（增强版）"""
        self.logger.info("=" * 50)
        self.logger.info("员工监控系统客户端 v3.2 (增强版)")
        self.logger.info("=" * 50)

        if not self.validate_config():
            self.logger.error("配置验证失败，程序退出")
            return

        if not self.register_with_server(silent_mode=silent_mode):
            self.logger.warning("注册失败，将以离线模式运行")
            self.offline_mode = True

        self.running = True
        self.stats["start_time"] = time.time()

        # 先启动各个子系统
        self.health_monitor.start_monitoring()
        self.upload_queue.start()

        # 然后启动看门狗
        self.watchdog.start()

        # 等待一下，确保看门狗完全启动
        time.sleep(1)

        # 注册并启动主工作循环
        self.logger.info("注册主工作循环到看门狗...")
        self.watchdog.watch(
            "main_work_loop",
            self.work_loop,
            args=(),
            kwargs={},
            auto_restart=True,
            health_check=lambda: self.running and not self.paused,
        )
        success = self.watchdog.start_watch("main_work_loop")
        if success:
            self.logger.info("✅ 主工作循环已启动")
        else:
            self.logger.error("❌ 主工作循环启动失败")

        # 启动配置监控线程（独立线程，不看门狗管理）
        config_thread = threading.Thread(
            target=self.config_watcher, name="ConfigWatcher", daemon=True
        )
        config_thread.start()
        self.logger.debug(f"线程已启动: {config_thread.name}")

        # 启动网络监控线程（独立线程，不看门狗管理）
        network_thread = threading.Thread(
            target=self.network_monitor, name="NetworkMonitor", daemon=True
        )
        network_thread.start()
        self.logger.debug(f"线程已启动: {network_thread.name}")

        # 启动批量上传线程（独立线程，不看门狗管理）
        batch_thread = threading.Thread(
            target=self.batch_uploader, name="BatchUploader", daemon=True
        )
        batch_thread.start()
        self.logger.debug(f"线程已启动: {batch_thread.name}")

        # 心跳功能（可选，由看门狗管理）
        if self.enable_heartbeat:
            self.logger.info("注册心跳发送器到看门狗...")
            self.watchdog.watch(
                "heartbeat_sender",
                self.heartbeat_sender,
                args=(),
                kwargs={},
                auto_restart=True,
                health_check=lambda: self.enable_heartbeat,
            )
            success = self.watchdog.start_watch("heartbeat_sender")
            if success:
                self.logger.info("✅ 心跳发送器已启动")
            else:
                self.logger.warning("⚠️ 心跳发送器启动失败")

        self.logger.info("监控程序启动成功")

        # 托盘图标处理
        if self.tray:
            tray_thread = threading.Thread(
                target=self.tray.run, name="TrayIcon", daemon=True
            )
            tray_thread.start()
            self.logger.info("✅ 托盘图标线程已启动")

            try:
                while self.running:
                    time.sleep(1)
                    if self.tray and hasattr(self.tray, "update_icon_title"):
                        self.tray.update_icon_title()
            except KeyboardInterrupt:
                self.stop()
        else:
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        """停止监控（增强版）"""
        self.logger.info("正在停止监控程序...")
        self.running = False

        if hasattr(self, "watchdog"):
            self.watchdog.stop()

        if hasattr(self, "health_monitor"):
            self.health_monitor.stop_monitoring()

        if hasattr(self, "upload_queue"):
            self.upload_queue.stop()

        if hasattr(self, "screenshot_manager"):
            self.screenshot_manager.cleanup_old_screenshots()

        if not self.offline_mode:
            self.send_heartbeat()

        uptime = time.time() - self.stats["start_time"]
        self.logger.info("=" * 50)
        self.logger.info("监控程序停止")
        self.logger.info(f"运行时间: {uptime/3600:.2f}小时")
        self.logger.info(f"截图数量: {self.stats['screenshots_taken']}")
        self.logger.info(f"跳过相似: {self.stats.get('skipped_similar', 0)}")
        self.logger.info(f"上传成功: {self.stats['screenshots_uploaded']}")
        self.logger.info(f"上传失败: {self.stats['upload_failures']}")

        if hasattr(self, "upload_queue"):
            queue_stats = self.upload_queue.get_stats()
            self.logger.info(f"队列处理: {queue_stats['processed']}")
            self.logger.info(f"队列重试: {queue_stats['retried']}")

        if hasattr(self, "health_monitor"):
            health_summary = self.health_monitor.get_summary()
            self.logger.info(f"健康率: {health_summary['health_rate']*100:.1f}%")
            self.logger.info(f"恢复次数: {health_summary['total_recoveries']}")

        if hasattr(self, "watchdog"):
            watchdog_status = self.watchdog.get_status()
            self.logger.info(
                f"看门狗重启: {watchdog_status['stats']['total_restarts']}"
            )

        self.logger.info("=" * 50)

    # ========== 工具方法 ==========
    def get_stats(self):
        """获取统计信息（增强版）"""
        with self.stats_lock:
            stats_copy = self.stats.copy()
            if stats_copy["start_time"]:
                stats_copy["uptime"] = time.time() - stats_copy["start_time"]

            if hasattr(self, "upload_queue"):
                stats_copy["queue"] = self.upload_queue.get_stats()

            if hasattr(self, "health_monitor"):
                stats_copy["health"] = self.health_monitor.get_summary()

            if hasattr(self, "watchdog"):
                stats_copy["watchdog"] = self.watchdog.get_status()

            if hasattr(self, "phash_detector") and hasattr(
                self.phash_detector, "cache"
            ):
                stats_copy["phash_cache"] = len(self.phash_detector.cache)

            return stats_copy

    def test_mode(self):
        """测试模式"""
        print("\n" + "=" * 50)
        print("测试模式 - 立即截图并上传")
        print("=" * 50)

        if not self.register_with_server():
            self.logger.error("注册失败")
            return

        print(f"客户端ID: {self.client_id}")
        print(f"员工ID: {self.employee_id}")
        print(f"服务器: {self.current_server}")
        print(f"图片格式: {self.format}")
        print("-" * 50)

        print("正在截图...")
        image_path = self.screenshot_manager.take_screenshot()

        if image_path:
            print(f"✅ 截图成功: {os.path.basename(image_path)}")
            print(f"文件大小: {os.path.getsize(image_path)/1024:.1f}KB")

            print("正在上传...")
            if self.upload_screenshot(image_path):
                print("✅ 上传成功")
            else:
                print("❌ 上传失败")
        else:
            print("❌ 截图失败")

        print("=" * 50)

    def add_error(self, error):
        """记录错误"""
        with self.error_lock:
            self.stats["errors"].append(
                {"time": datetime.now().isoformat(), "error": str(error)}
            )
            if len(self.stats["errors"]) > 10:
                self.stats["errors"] = self.stats["errors"][-10:]


# ========== 保留原有的APIClient和ScreenshotManager类 ==========
class APIClient:
    """API客户端 - 使用智能重试装饰器"""

    def __init__(self, base_url, timeout=30, retry_times=3, retry_delay=1):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.last_error = None
        self.error_count = 0

        self.logger = logging.getLogger(__name__)

        self.session.headers.update(
            {
                "User-Agent": f"MonitorClient/{platform.platform()}",
                "Accept": "application/json",
            }
        )

        adapter = requests.adapters.HTTPAdapter(
            max_retries=0, pool_connections=10, pool_maxsize=10
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @smart_retry(max_retries=3, base_delay=2, max_delay=30, jitter=5)
    def post(self, endpoint, **kwargs):
        """POST请求"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", False)

        if "files" in kwargs and kwargs["files"]:
            if "headers" in kwargs:
                kwargs["headers"] = {
                    k: v
                    for k, v in kwargs["headers"].items()
                    if k.lower() != "content-type"
                }
            else:
                kwargs["headers"] = {}

        elif "json" in kwargs:
            headers = kwargs.get("headers", {})
            headers["Content-Type"] = "application/json"
            kwargs["headers"] = headers

        try:
            response = self.session.post(url, **kwargs)
            response.raise_for_status()
            self.error_count = 0
            self.last_error = None
            return response.json() if response.content else None

        except requests.exceptions.HTTPError as e:
            self.error_count += 1
            self.last_error = str(e)
            try:
                error_detail = response.json().get("detail", str(e))
            except:
                error_detail = response.text or str(e)
            self.logger.error(f"❌ POST失败 {url}: {error_detail}")
            raise Exception(error_detail)

    @smart_retry(max_retries=3, base_delay=1, max_delay=10, jitter=2)
    def get(self, endpoint, **kwargs):
        """GET请求"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", False)

        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            self.error_count = 0
            self.last_error = None
            return response.json()

        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            self.logger.error(f"❌ GET失败 {url}: {e}")
            raise


class ScreenshotManager:
    def __init__(
        self,
        quality=80,
        format="webp",
        max_history=10,
        similarity_threshold=0.95,
        encryption_key=None,
    ):
        self.quality = quality
        self.format = format.lower()
        self.max_history = max_history
        self.similarity_threshold = similarity_threshold
        self.encryption_key = encryption_key
        self.logger = logging.getLogger(__name__)  # ✅ 添加这行

        self.last_screenshot_path = None
        self.screenshot_history = []
        self.stats = {"taken": 0, "uploaded": 0, "skipped": 0, "failed": 0}

        if self.format not in ["webp", "jpg", "jpeg"]:
            self.logger.warning(f"不支持的图片格式 {self.format}，使用 webp")
            self.format = "webp"

    def take_screenshot(self):
        """截取屏幕（使用缓冲区池）"""
        try:
            # 使用多显示器截图（如果可用）
            multi_monitor = MultiMonitorScreenshot()
            screenshot = multi_monitor.capture_all_monitors()

            if not screenshot:
                screenshot = ImageGrab.grab(all_screens=True)

            # 使用缓冲区池
            buffer = get_buffer()

            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.{self.format}"
                filepath = os.path.join(os.getcwd(), filename)

                if self.format == "webp":
                    screenshot.save(
                        buffer, "WEBP", quality=self.quality, optimize=True, method=6
                    )
                else:
                    screenshot.save(buffer, "JPEG", quality=self.quality, optimize=True)

                # 使用原子写入
                AtomicFileOperation.atomic_write(filepath, buffer.getvalue())

                file_size = os.path.getsize(filepath)

                # 更新历史
                self.screenshot_history.append(filepath)
                if len(self.screenshot_history) > self.max_history:
                    old_file = self.screenshot_history.pop(0)
                    if (
                        os.path.exists(old_file)
                        and old_file != self.last_screenshot_path
                    ):
                        try:
                            AtomicFileOperation.atomic_delete(old_file)
                        except Exception:
                            pass

                self.stats["taken"] += 1
                self.logger.info(
                    f"✅ 截图成功: {filename} ({file_size/1024:.1f}KB, {self.format})"
                )
                return filepath

            finally:
                put_buffer(buffer)

        except Exception as e:
            self.logger.error(f"❌ 截图失败: {e}")
            return None

    def are_similar(self, img1_path, img2_path):
        """判断两张图片是否相似（使用感知哈希）"""
        phash = PerceptualHash(threshold=self.similarity_threshold)
        similar = phash.are_similar(img1_path, img2_path)

        if similar:
            self.stats["skipped"] += 1

        return similar

    def encrypt_screenshot(self, image_path):
        """加密截图文件"""
        try:
            from cryptography.fernet import Fernet

            cipher = Fernet(self.encryption_key.encode())

            image_data = AtomicFileOperation.atomic_read(image_path)
            if image_data is None:
                self.logger.error(f"读取截图失败: {image_path}")
                return image_path

            encrypted_data = cipher.encrypt(image_data)
            encrypted_path = image_path + ".encrypted"

            AtomicFileOperation.atomic_write(encrypted_path, encrypted_data)
            AtomicFileOperation.atomic_delete(image_path)

            self.logger.debug(f"🔐 截图已加密: {os.path.basename(encrypted_path)}")
            return encrypted_path

        except Exception as e:
            self.logger.error(f"❌ 加密失败: {e}")
            return image_path

    def cleanup_old_screenshots(self, max_age_hours=24):
        """清理旧截图（使用原子操作）"""
        try:
            now = time.time()
            pattern = f"screenshot_*.{self.format}"
            count = 0
            size_freed = 0

            for file in Path(".").glob(pattern):
                if file.name.startswith(".tmp_"):
                    continue

                file_age = now - file.stat().st_mtime
                if file_age > max_age_hours * 3600:
                    size = file.stat().st_size
                    if AtomicFileOperation.atomic_delete(str(file)):
                        size_freed += size
                        count += 1

            if count > 0:
                self.logger.info(
                    f"清理了 {count} 个旧截图，释放 {size_freed/1024/1024:.2f}MB"
                )

        except Exception as e:
            self.logger.error(f"清理旧截图失败: {e}")

    def get_stats(self):
        """获取截图统计"""
        return self.stats.copy()


# ========== 主函数 ==========
def main():
    """主函数"""
    logger = logging.getLogger(__name__)
    setup_logging(log_level=logging.INFO, log_file="monitor.log")
    parser = argparse.ArgumentParser(
        description="员工监控系统客户端 - 工业级增强版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-c", "--config", default="config.json", help="配置文件路径 (默认: config.json)"
    )
    parser.add_argument("--test", action="store_true", help="测试模式：立即截图并上传")
    parser.add_argument("--register", action="store_true", help="仅注册，不启动监控")
    parser.add_argument(
        "--reconfigure", action="store_true", help="强制重新配置员工信息"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认: INFO)",
    )
    parser.add_argument("--server", action="append", help="指定服务器地址 (可多次使用)")
    parser.add_argument("--interval", type=int, help="截图间隔（秒）")
    parser.add_argument(
        "--quality", type=int, choices=range(10, 101), help="图片质量 (10-100)"
    )
    parser.add_argument("--format", choices=["webp", "jpg", "jpeg"], help="图片格式")
    parser.add_argument("--encrypt", action="store_true", help="启用加密")
    parser.add_argument(
        "--silent", action="store_true", help="静默模式，不显示交互界面"
    )
    parser.add_argument("--version", action="version", version="员工监控系统客户端 3.2")

    args = parser.parse_args()

    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # 创建客户端实例
    client = MonitorClient(args.config, force_reconfigure=args.reconfigure)

    # 命令行参数覆盖配置
    if args.server:
        client.server_urls = args.server
        client.config_manager.set("server_urls", args.server)

    if args.interval:
        client.interval = args.interval
        client.config_manager.set("interval", args.interval)

    if args.quality:
        client.quality = args.quality
        client.config_manager.set("quality", args.quality)

    if args.format:
        client.format = args.format
        client.config_manager.set("format", args.format)

    if args.encrypt:
        client.encryption_enabled = True
        client.config_manager.set("encryption_enabled", True)

    # 执行相应模式
    try:
        if args.test:
            client.test_mode()
        elif args.register:
            client.register_with_server(silent_mode=args.silent)
        else:
            client.start(silent_mode=args.silent)
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
