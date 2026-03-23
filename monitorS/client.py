#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工监控系统客户端 - 企业级重构版本 v4.0
==========================================
设计目标：
1. 企业级架构 - 模块化、可扩展、高内聚低耦合
2. 极致功耗 - 智能休眠、资源复用、延迟加载
3. 用户体验 - 实时反馈、智能恢复、操作便捷
4. 数据安全 - 加密传输、原子操作、防篡改
5. 稳定性 - 熔断机制、降级服务、自动恢复

版本历史：
v4.0 - 企业级重构版本
- 重构为模块化架构
- 新增智能功耗管理系统
- 优化错误恢复机制
- 增强数据安全
"""

# ===== 标准库导入 =====
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
import atexit
import base64
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum
from enum import Enum, auto

# ===== 第三方库导入 =====
import requests
from PIL import ImageGrab, Image
from portalocker import lock, unlock, LOCK_EX, LOCK_NB

# ===== 内部模块导入 =====
from client_core import (
    SystemInfoCollector,
    ConfigManager,
    APIClient,
    setup_logging,
    AtomicFileOperation,
    BufferPool,
    get_buffer,
    put_buffer,
    HealthMonitor,
    HealthStatus,
    HealthRecord,
    ComponentHealth,
    ProcessWatchdog,
    PerceptualHash,
    MultiMonitorScreenshot,
    UploadQueue,
    UploadTask,
    retry,
    smart_retry,
)
from client_config import Config
from client_i18n import I18nManager, get_text

# ===== 版本信息 =====
__version__ = "4.0.0"
__build__ = "20240319"
__release__ = "enterprise"


# ===== 版本工具函数 =====
def get_version_info() -> Dict[str, str]:
    """获取完整的版本信息"""
    return {
        "version": __version__,
        "build": __build__,
        "release": __release__,
    }


def get_version_from_file() -> str:
    """从VERSION文件读取版本（如果存在）"""
    version_file = Path(__file__).parent / "VERSION"
    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except:
            pass
    return __version__


# ========== 单实例锁管理 ==========
class SingleInstanceLock:
    """跨平台单实例锁管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.lock_file = None
        self.lock_fd = None
        self.logger = logging.getLogger(__name__)

    def acquire(self, lock_name: str = "employee_monitor") -> bool:
        """获取单实例锁"""
        # 在不同系统上使用不同的锁目录
        if sys.platform == "win32":
            lock_dir = tempfile.gettempdir()
        else:
            lock_dir = "/tmp"

        lock_path = os.path.join(lock_dir, f"{lock_name}.lock")

        try:
            self.lock_fd = open(lock_path, "w")
            lock(self.lock_fd, LOCK_EX | LOCK_NB)

            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            self.lock_file = lock_path

            self.logger.info(f"✅ 成功获取实例锁，PID: {os.getpid()}")
            return True

        except (IOError, OSError) as e:
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None

            try:
                with open(lock_path, "r") as f:
                    existing_pid = f.read().strip()
                self.logger.error(f"❌ 另一个客户端实例已在运行 (PID: {existing_pid})")
            except:
                self.logger.error("❌ 另一个客户端实例已在运行")

            return False

    def release(self):
        """释放单实例锁"""
        try:
            if self.lock_fd:
                unlock(self.lock_fd)
                self.lock_fd.close()
                self.lock_fd = None

            if self.lock_file and os.path.exists(self.lock_file):
                os.unlink(self.lock_file)
                self.lock_file = None
                self.logger.debug("✅ 实例锁已释放")
        except Exception as e:
            self.logger.debug(f"释放锁时出错: {e}")


# 全局单实例锁对象
_instance_lock = SingleInstanceLock()
atexit.register(_instance_lock.release)


# ========== 智能功耗管理系统 ==========
class PowerManager:
    """
    智能功耗管理系统
    - 动态调整检查间隔
    - 空闲检测
    - 节电模式
    - 后台优化
    """

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        # 功耗状态
        self.power_saving_mode = False
        self.idle_mode = False
        self.battery_mode = False

        # 检测间隔（秒）
        self.base_interval = client.interval
        self.power_saving_interval = client.interval * 2
        self.idle_interval = client.interval * 3

        # 空闲检测
        self.last_activity_time = time.time()
        self.idle_threshold = 300  # 5分钟无操作视为空闲
        self.idle_check_interval = 60

        # 统计信息
        self.stats = {
            "power_saving_entered": 0,
            "power_saving_exited": 0,
            "idle_entered": 0,
            "idle_exited": 0,
            "battery_mode_entered": 0,
            "battery_mode_exited": 0,
            "total_time_saved": 0,
        }

        self.running = False
        self.monitor_thread = None
        self.lock = threading.RLock()

        # 尝试检测电池状态
        self._init_battery_detection()

    def _init_battery_detection(self):
        """初始化电池检测"""
        try:
            import psutil

            self.psutil = psutil
            self.has_battery = psutil.sensors_battery() is not None
        except (ImportError, AttributeError):
            self.has_battery = False

    def start(self):
        """启动功耗管理"""
        if self.running:
            return
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, name="PowerManager", daemon=True
        )
        self.monitor_thread.start()
        self.logger.info("✅ 智能功耗管理系统已启动")

    def stop(self):
        """停止功耗管理"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)

    def _monitor_loop(self):
        """功耗监控循环"""
        while self.running:
            try:
                now = time.time()

                # 检测电池状态
                self._check_battery_status()

                # 检测空闲状态
                self._check_idle_status()

                # 调整截图间隔
                self._adjust_interval()

                # 收集统计
                if hasattr(self.client, "health_monitor"):
                    self.client.health_monitor.update_status(
                        "power",
                        HealthStatus.HEALTHY,
                        f"节电:{self.power_saving_mode} 空闲:{self.idle_mode} 电池:{self.battery_mode}",
                        metrics=self.get_stats(),
                    )

                time.sleep(self.idle_check_interval)

            except Exception as e:
                self.logger.error(f"功耗监控异常: {e}")
                time.sleep(60)

    def _check_battery_status(self):
        """检查电池状态"""
        if not self.has_battery:
            return

        try:
            battery = self.psutil.sensors_battery()
            if battery:
                was_battery_mode = self.battery_mode
                self.battery_mode = not battery.power_plugged

                if self.battery_mode and not was_battery_mode:
                    with self.lock:
                        self.stats["battery_mode_entered"] += 1
                    self.logger.info("🔋 切换到电池模式")
                elif not self.battery_mode and was_battery_mode:
                    with self.lock:
                        self.stats["battery_mode_exited"] += 1
                    self.logger.info("🔌 切换到电源模式")
        except Exception as e:
            self.logger.debug(f"电池检测失败: {e}")

    def _check_idle_status(self):
        """检查空闲状态"""
        try:
            # 获取最后输入时间（仅Windows）
            if sys.platform == "win32":
                import ctypes
                from ctypes import wintypes

                class LASTINPUTINFO(ctypes.Structure):
                    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

                lii = LASTINPUTINFO()
                lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
                if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                    idle_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                    idle_seconds = idle_ms / 1000.0

                    was_idle = self.idle_mode
                    self.idle_mode = idle_seconds > self.idle_threshold

                    if self.idle_mode and not was_idle:
                        with self.lock:
                            self.stats["idle_entered"] += 1
                        self.logger.info("💤 进入空闲模式")
                    elif not self.idle_mode and was_idle:
                        with self.lock:
                            self.stats["idle_exited"] += 1
                        self.logger.info("✨ 退出空闲模式")
            else:
                # Linux/Mac 简化处理
                self.idle_mode = False
        except Exception as e:
            self.logger.debug(f"空闲检测失败: {e}")

    def _adjust_interval(self):
        """动态调整截图间隔"""
        old_interval = self.client.interval
        new_interval = self.base_interval

        # 应用功耗策略
        if self.battery_mode or self.power_saving_mode:
            new_interval = self.power_saving_interval
        elif self.idle_mode:
            new_interval = self.idle_interval

        if new_interval != old_interval:
            self.client.interval = new_interval
            self.logger.debug(
                f"截图间隔调整: {old_interval}s → {new_interval}s "
                f"(电池:{self.battery_mode} 空闲:{self.idle_mode})"
            )

            # 计算节省的时间
            if new_interval > old_interval:
                with self.lock:
                    self.stats["total_time_saved"] += new_interval - old_interval

    def record_activity(self):
        """记录用户活动"""
        self.last_activity_time = time.time()
        if self.idle_mode:
            self.idle_mode = False

    def set_power_saving(self, enabled: bool):
        """手动设置节电模式"""
        with self.lock:
            if enabled and not self.power_saving_mode:
                self.stats["power_saving_entered"] += 1
            elif not enabled and self.power_saving_mode:
                self.stats["power_saving_exited"] += 1

            self.power_saving_mode = enabled
            self.logger.info(f"{'启用' if enabled else '禁用'}节电模式")

    def get_stats(self) -> Dict[str, Any]:
        """获取功耗统计"""
        with self.lock:
            return {
                **self.stats.copy(),
                "current_interval": self.client.interval,
                "base_interval": self.base_interval,
                "power_saving_mode": self.power_saving_mode,
                "idle_mode": self.idle_mode,
                "battery_mode": self.battery_mode,
            }


# ========== 错误恢复系统 ==========
# ========== 错误恢复系统 ==========
class ErrorRecoverySystem:
    """
    智能错误恢复系统
    - 错误分类处理
    - 指数退避重试
    - 熔断保护
    - 降级服务
    """

    class ErrorType(Enum):
        NETWORK = auto()  # 网络错误
        SERVER = auto()  # 服务器错误
        LOCAL = auto()  # 本地错误
        RESOURCE = auto()  # 资源不足
        UNKNOWN = auto()  # 未知错误

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        # 错误计数器
        self.error_counts = {
            self.ErrorType.NETWORK: 0,
            self.ErrorType.SERVER: 0,
            self.ErrorType.LOCAL: 0,
            self.ErrorType.RESOURCE: 0,
            self.ErrorType.UNKNOWN: 0,
        }

        # 错误历史
        self.error_history = deque(maxlen=100)

        # 熔断配置
        self.circuit_breakers = {
            self.ErrorType.NETWORK: {
                "threshold": 5,  # 5次错误触发熔断
                "timeout": 300,  # 熔断5分钟
                "last_break": 0,
                "broken": False,
            },
            self.ErrorType.SERVER: {
                "threshold": 3,
                "timeout": 600,  # 服务器错误熔断10分钟
                "last_break": 0,
                "broken": False,
            },
        }

        # 降级配置
        self.degraded_services = set()

        self.lock = threading.RLock()
        self.running = False

    def start(self):
        """启动错误恢复系统"""
        self.running = True
        self.logger.info("✅ 智能错误恢复系统已启动")

    def stop(self):
        """停止错误恢复系统"""
        self.running = False

    def classify_error(self, error: Exception) -> ErrorType:
        """错误分类"""
        error_str = str(error).lower()

        # 网络错误
        if isinstance(
            error,
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                socket.error,
            ),
        ):
            return self.ErrorType.NETWORK

        # 服务器错误
        if isinstance(error, requests.exceptions.HTTPError):
            if hasattr(error, "response") and error.response:
                if error.response.status_code >= 500:
                    return self.ErrorType.SERVER
                elif error.response.status_code == 429:  # Too Many Requests
                    return self.ErrorType.RESOURCE
            return self.ErrorType.SERVER

        # 资源不足
        if any(word in error_str for word in ["memory", "disk", "full", "quota"]):
            return self.ErrorType.RESOURCE

        # 本地文件错误
        if isinstance(error, (IOError, OSError, PermissionError)):
            return self.ErrorType.LOCAL

        return self.ErrorType.UNKNOWN

    def report_error(self, error: Exception, component: str, context: Dict = None):
        """报告错误"""
        error_type = self.classify_error(error)

        with self.lock:
            # 更新计数器
            self.error_counts[error_type] += 1

            # 记录错误历史
            self.error_history.append(
                {
                    "time": time.time(),
                    "type": error_type.name,
                    "component": component,
                    "error": str(error),
                    "context": context or {},
                }
            )

            # 检查熔断
            self._check_circuit_breaker(error_type)

        # 触发恢复策略
        self._trigger_recovery(error_type, component, error)

        # 更新健康状态
        if hasattr(self.client, "health_monitor"):
            status = (
                HealthStatus.DEGRADED
                if error_type in [self.ErrorType.NETWORK, self.ErrorType.RESOURCE]
                else HealthStatus.UNHEALTHY
            )
            self.client.health_monitor.update_status(
                component,
                status,
                f"{error_type.name}: {str(error)[:100]}",
            )

    def _check_circuit_breaker(self, error_type: ErrorType):
        """检查并更新熔断状态"""
        if error_type not in self.circuit_breakers:
            return

        cb = self.circuit_breakers[error_type]
        now = time.time()

        # 如果已熔断，检查是否过期
        if cb["broken"]:
            if now - cb["last_break"] > cb["timeout"]:
                cb["broken"] = False
                self.logger.info(f"🔌 {error_type.name} 熔断恢复")
            return

        # 检查是否需要熔断
        recent_errors = sum(
            1
            for e in self.error_history
            if e["type"] == error_type.name and now - e["time"] < 60
        )  # 最近1分钟

        if recent_errors >= cb["threshold"]:
            cb["broken"] = True
            cb["last_break"] = now
            self.logger.warning(f"⚠️ {error_type.name} 触发熔断，暂停 {cb['timeout']}秒")

    def _trigger_recovery(
        self, error_type: ErrorType, component: str, error: Exception
    ):
        """触发恢复策略"""
        # 根据错误类型执行不同恢复策略
        if error_type == self.ErrorType.NETWORK:
            self._recover_network(component)
        elif error_type == self.ErrorType.SERVER:
            self._recover_server(component)
        elif error_type == self.ErrorType.RESOURCE:
            self._recover_resource(component)
        elif error_type == self.ErrorType.LOCAL:
            self._recover_local(component)

    def _recover_network(self, component: str):
        """网络错误恢复"""
        if not self.is_circuit_broken(self.ErrorType.NETWORK):
            # 触发网络检测
            if hasattr(self.client, "force_network_check"):
                self.client.force_network_check = True
        else:
            # 熔断期间，进入离线模式
            if hasattr(self.client, "offline_mode") and not self.client.offline_mode:
                self.client.offline_mode = True
                self.logger.info("📴 网络熔断，进入离线模式")

    def _recover_server(self, component: str):
        """服务器错误恢复"""
        if self.is_circuit_broken(self.ErrorType.SERVER):
            # 切换服务器
            if hasattr(self.client, "_switch_server"):
                self.client._switch_server()
        else:
            # 简单重试
            pass

    def _recover_resource(self, component: str):
        """资源不足恢复"""
        # 触发垃圾回收
        gc.collect()

        # 清理临时文件
        if hasattr(self.client, "upload_queue"):
            self.client.upload_queue._cleanup_cache()

    def _recover_local(self, component: str):
        """本地错误恢复"""
        # 重置组件状态
        if component == "screenshot" and hasattr(self.client, "screenshot_manager"):
            self.client.screenshot_manager.last_screenshot_path = None

    def is_circuit_broken(self, error_type: ErrorType) -> bool:
        """检查是否熔断"""
        cb = self.circuit_breakers.get(error_type)
        if cb and cb["broken"]:
            now = time.time()
            if now - cb["last_break"] > cb["timeout"]:
                cb["broken"] = False
                return False
            return True
        return False

    def should_retry(self, error: Exception, retry_count: int) -> bool:
        """判断是否应该重试"""
        error_type = self.classify_error(error)

        # 熔断中不重试
        if self.is_circuit_broken(error_type):
            return False

        # 不同错误类型的最大重试次数
        max_retries = {
            self.ErrorType.NETWORK: 5,
            self.ErrorType.SERVER: 3,
            self.ErrorType.LOCAL: 2,
            self.ErrorType.RESOURCE: 1,
            self.ErrorType.UNKNOWN: 1,
        }

        return retry_count < max_retries.get(error_type, 1)

    def get_recovery_delay(self, error: Exception, retry_count: int) -> float:
        """获取恢复延迟时间（指数退避）"""
        error_type = self.classify_error(error)

        base_delays = {
            self.ErrorType.NETWORK: 5,
            self.ErrorType.SERVER: 10,
            self.ErrorType.LOCAL: 2,
            self.ErrorType.RESOURCE: 30,
            self.ErrorType.UNKNOWN: 5,
        }

        base = base_delays.get(error_type, 5)
        delay = base * (2 ** (retry_count - 1))
        return min(delay, 300)  # 最大5分钟

    def get_stats(self) -> Dict[str, Any]:
        """获取错误统计"""
        with self.lock:
            return {
                # ✅ 修复：将 ErrorType 枚举转换为字符串
                "error_counts": {k.name: v for k, v in self.error_counts.items()},
                "recent_errors": list(self.error_history)[-10:],
                "circuit_breakers": {
                    k.name: {
                        "broken": v["broken"],
                        "remaining": (
                            max(0, v["timeout"] - (time.time() - v["last_break"]))
                            if v["broken"]
                            else 0
                        ),
                    }
                    for k, v in self.circuit_breakers.items()
                },
                "degraded_services": list(self.degraded_services),
            }


# ========== 数据安全模块 ==========
class DataSecurityManager:
    """
    数据安全管理器
    - 加密/解密
    - 完整性校验
    - 数据签名
    - 敏感信息脱敏
    """

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        # 加密密钥
        self.encryption_key = None
        self._init_encryption()

        # 缓存
        self.hash_cache = {}
        self.cache_lock = threading.RLock()

    def _init_encryption(self):
        """初始化加密"""
        if not self.client.encryption_enabled:
            return

        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

            # 从环境变量或配置获取密钥
            key_material = os.environ.get("ENCRYPTION_KEY") or self.client.client_id

            if key_material:
                # 使用 PBKDF2 派生密钥
                salt = b"employee_monitor_salt"
                kdf = PBKDF2(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                key = base64.urlsafe_b64encode(kdf.derive(key_material.encode()))
                self.encryption_key = key
                self.fernet = Fernet(key)
                self.logger.info("🔐 加密模块初始化成功")
            else:
                self.logger.warning("⚠️ 未设置加密密钥，加密功能禁用")
                self.client.encryption_enabled = False

        except ImportError:
            self.logger.warning("⚠️ cryptography 未安装，加密功能禁用")
            self.client.encryption_enabled = False
        except Exception as e:
            self.logger.error(f"❌ 加密模块初始化失败: {e}")
            self.client.encryption_enabled = False

    def encrypt_data(self, data: bytes) -> Optional[bytes]:
        """加密数据"""
        if not self.client.encryption_enabled or not self.encryption_key:
            return data

        try:
            return self.fernet.encrypt(data)
        except Exception as e:
            self.logger.error(f"加密失败: {e}")
            return data

    def decrypt_data(self, data: bytes) -> Optional[bytes]:
        """解密数据"""
        if not self.client.encryption_enabled or not self.encryption_key:
            return data

        try:
            return self.fernet.decrypt(data)
        except Exception:
            return data

    def calculate_hash(self, data: bytes, algorithm: str = "sha256") -> str:
        """计算数据哈希"""
        if algorithm == "md5":
            return hashlib.md5(data).hexdigest()
        elif algorithm == "sha1":
            return hashlib.sha1(data).hexdigest()
        else:
            return hashlib.sha256(data).hexdigest()

    def verify_integrity(self, data: bytes, expected_hash: str) -> bool:
        """验证数据完整性"""
        actual_hash = self.calculate_hash(data)
        return actual_hash == expected_hash

    def sign_data(self, data: Dict) -> Dict:
        """给数据添加签名"""
        if not self.client.client_id:
            return data

        try:
            # 创建数据副本
            signed_data = data.copy()

            # 添加时间戳
            signed_data["_timestamp"] = time.time()

            # 创建签名字符串
            sign_str = json.dumps(signed_data, sort_keys=True) + self.client.client_id

            # 计算签名
            signature = hashlib.sha256(sign_str.encode()).hexdigest()

            signed_data["_signature"] = signature
            return signed_data

        except Exception as e:
            self.logger.debug(f"签名失败: {e}")
            return data

    def verify_signature(self, data: Dict, client_id: str) -> bool:
        """验证数据签名"""
        if "_signature" not in data:
            return False

        signature = data.pop("_signature")
        timestamp = data.pop("_timestamp", 0)

        # 检查时间戳是否过期（5分钟）
        if time.time() - timestamp > 300:
            return False

        try:
            # 重新计算签名
            sign_str = json.dumps(data, sort_keys=True) + client_id
            expected = hashlib.sha256(sign_str.encode()).hexdigest()

            return signature == expected
        finally:
            # 恢复数据
            data["_signature"] = signature
            if timestamp:
                data["_timestamp"] = timestamp

    def mask_sensitive_data(
        self, text: str, keep_first: int = 2, keep_last: int = 2
    ) -> str:
        """脱敏处理"""
        if not text:
            return text

        if len(text) <= keep_first + keep_last:
            return text

        return (
            text[:keep_first]
            + "*" * (len(text) - keep_first - keep_last)
            + text[-keep_last:]
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取安全统计"""
        return {
            "encryption_enabled": self.client.encryption_enabled,
            "hash_cache_size": len(self.hash_cache),
        }


# ========== 监控客户端主类（重构版）==========
class MonitorClient:
    """
    监控客户端主类 - 企业级重构版本
    ====================================
    模块组成：
    - config_manager: 配置管理
    - system_info: 系统信息收集
    - api_client: API通信
    - health_monitor: 健康监控
    - upload_queue: 上传队列
    - screenshot_manager: 截图管理
    - multi_monitor: 多显示器支持
    - phash_detector: 相似度检测
    - watchdog: 进程看门狗
    - power_manager: 功耗管理
    - error_recovery: 错误恢复
    - security: 数据安全
    - i18n: 国际化
    """

    def __init__(
        self, config_file: str = "config.json", force_reconfigure: bool = False
    ):
        # ===== 基础组件 =====
        self.logger = logging.getLogger(__name__)
        self.version = __version__

        # 配置管理器
        self.config_manager = ConfigManager(config_file)

        # 系统信息收集器
        self.system_info = SystemInfoCollector()

        # 国际化
        self.i18n = I18nManager()
        self._ = self.i18n.get_text

        # ===== 加载配置 =====
        self._load_config()

        # ===== 强制重新配置 =====
        self._force_reconfigure = force_reconfigure
        self.first_run = self._check_first_run()

        # ===== 状态变量 =====
        self.running = False
        self.paused = False
        self.offline_mode = False
        self.current_server_index = 0
        self.current_server = self.server_urls[0] if self.server_urls else None

        # 远程屏幕模块
        self.remote_screen = None
        self.enable_remote_screen = self.config_manager.get(
            "enable_remote_screen", True
        )

        # 截图控制
        self.take_screenshot_now = False
        self._last_screenshot_time = 0
        self._min_screenshot_interval = 3

        # 统计信息
        self._stats = {
            "screenshots_taken": 0,
            "screenshots_uploaded": 0,
            "upload_failures": 0,
            "skipped_similar": 0,
            "start_time": None,
            "last_upload_time": None,
            "last_heartbeat": None,
            "errors": [],
        }
        self._stats_lock = threading.RLock()
        self._error_lock = threading.RLock()

        # ===== 延迟初始化（启动时创建）=====
        self.api_client = None
        self.health_monitor = None
        self.upload_queue = None
        self.screenshot_manager = None
        self.multi_monitor = None
        self.phash_detector = None
        self.watchdog = None
        self.power_manager = None
        self.error_recovery = None
        self.security = None
        self.tray = None

        # 线程管理
        self._threads = []
        self._thread_lock = threading.RLock()

        self.logger.info(f"📦 客户端初始化完成，版本 {self.version}")

        # ===== 新增监控模块 =====
        self.browser_monitor = None
        self.app_monitor = None
        self.file_monitor = None
        self.enable_browser_monitor = self.config_manager.get(
            "enable_browser_monitor", True
        )
        self.enable_app_monitor = self.config_manager.get("enable_app_monitor", True)
        self.enable_file_monitor = self.config_manager.get("enable_file_monitor", True)

    def _load_config(self):
        """加载配置"""
        from client_config import Config as ClientConfig

        # 基础配置
        self.client_id = self.config_manager.get("client_id", "")
        self.employee_id = self.config_manager.get("employee_id", "")
        self.employee_name = self.config_manager.get("employee_name", "")

        # 服务器配置
        self.server_urls = self.config_manager.get(
            "server_urls", ClientConfig.DEFAULT_SERVERS
        )

        # 截图配置
        self.interval = self.config_manager.get(
            "interval", ClientConfig.SCREENSHOT_INTERVAL
        )
        self.quality = self.config_manager.get(
            "quality", ClientConfig.SCREENSHOT_QUALITY
        )
        self.format = self.config_manager.get("format", ClientConfig.SCREENSHOT_FORMAT)

        # 功能开关
        self.auto_start = self.config_manager.get("auto_start", True)
        self.hide_window = self.config_manager.get("hide_window", True)
        self.enable_heartbeat = self.config_manager.get("enable_heartbeat", True)
        self.enable_batch_upload = self.config_manager.get("enable_batch_upload", True)
        self.encryption_enabled = self.config_manager.get("encryption_enabled", False)

        # 高级配置
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

        # 验证配置
        self._validate_config()

    def _validate_config(self):
        """验证并修正配置"""
        # 服务器URL验证
        valid_urls = []
        for url in self.server_urls:
            if url and url.startswith(("http://", "https://")):
                valid_urls.append(url)
            else:
                self.logger.warning(f"无效的服务器URL: {url}")

        if not valid_urls:
            from client_config import Config

            valid_urls = Config.DEFAULT_SERVERS
            self.logger.warning("使用默认服务器配置")

        self.server_urls = valid_urls

        # 间隔验证
        if not 10 <= self.interval <= 3600:
            self.interval = 60
            self.logger.warning("截图间隔调整为60秒")

        # 质量验证
        if not 10 <= self.quality <= 100:
            self.quality = 80
            self.logger.warning("图片质量调整为80")

        # 格式验证
        if self.format not in ["webp", "jpg", "jpeg"]:
            self.format = "webp"
            self.logger.warning("图片格式调整为webp")

    def _check_first_run(self) -> bool:
        """检查是否首次运行"""
        # 强制重新配置
        if self._force_reconfigure:
            self.logger.info("🔄 强制重新配置模式")
            return True

        # 配置文件不存在
        if not os.path.exists(self.config_manager.config_file):
            self.logger.info("🔔 首次运行：没有配置文件")
            return True

        # 缺少必要信息
        if not self.client_id or not self.employee_id or not self.employee_name:
            self.logger.info("🔔 首次运行：缺少必要信息")
            return True

        return False

    # ===== 初始化子系统 =====
    def _init_subsystems(self):
        """初始化所有子系统（延迟加载）"""
        self.logger.info("🔄 初始化子系统...")

        # API客户端
        self.api_client = APIClient(
            self.current_server,
            retry_times=self.retry_times,
            retry_delay=self.retry_delay,
        )

        # 健康监控
        self.health_monitor = HealthMonitor(check_interval=60, recovery_cooldown=300)
        self._register_health_components()

        # 错误恢复系统
        self.error_recovery = ErrorRecoverySystem(self)

        # 数据安全
        self.security = DataSecurityManager(self)

        # 多显示器截图
        self.multi_monitor = MultiMonitorScreenshot()

        # 感知哈希检测
        self.phash_detector = PerceptualHash(threshold=self.similarity_threshold)

        # 截图管理器
        self.screenshot_manager = ScreenshotManager(
            quality=self.quality,
            format=self.format,
            max_history=self.max_history,
            similarity_threshold=self.similarity_threshold,
            encryption_key=os.environ.get("ENCRYPTION_KEY"),
        )

        # 上传队列
        self.upload_queue = UploadQueue(
            client=self,
            max_queue_size=100,
            worker_count=3,
            cache_dir="cache",
            max_cache_size=500 * 1024 * 1024,
        )

        # 进程看门狗
        self.watchdog = ProcessWatchdog(check_interval=30, max_restarts=5)

        # 功耗管理
        self.power_manager = PowerManager(self)

        # 初始化所有组件状态
        self._init_health_status()

        self.logger.info("✅ 所有子系统初始化完成")

        if self.enable_remote_screen:
            try:
                from client_remote import RemoteScreenManager

                self.remote_screen = RemoteScreenManager(self)
                self.logger.info("✅ 专业远程屏幕模块已初始化")
            except ImportError as e:
                self.logger.warning(f"⚠️ 远程屏幕初始化失败: {e}")

        # ===== 新增监控模块初始化 =====
        if self.enable_browser_monitor:
            try:
                from client_browser import BrowserMonitor

                self.browser_monitor = BrowserMonitor(self)
                self.logger.info("✅ 浏览器监控已初始化")
            except ImportError as e:
                self.logger.warning(f"⚠️ 浏览器监控初始化失败: {e}")

        if self.enable_app_monitor:
            try:
                from client_apps import AppMonitor

                self.app_monitor = AppMonitor(self)
                self.logger.info("✅ 软件监控已初始化")
            except ImportError as e:
                self.logger.warning(f"⚠️ 软件监控初始化失败: {e}")

        if self.enable_file_monitor:
            try:
                from client_file_monitor import FileMonitor

                self.file_monitor = FileMonitor(self)
                self.logger.info("✅ 文件监控已初始化")
            except ImportError as e:
                self.logger.warning(f"⚠️ 文件监控初始化失败: {e}")

    def _register_health_components(self):
        """注册健康监控组件"""
        components = [
            ("screenshot", self._recover_screenshot),
            ("upload", self._recover_upload),
            ("network", self._recover_network),
            ("heartbeat", self._recover_heartbeat),
            ("config", self._recover_config),
            ("watchdog", self._recover_watchdog),
            ("power", None),
        ]

        for name, callback in components:
            self.health_monitor.register_component(name, callback)

    def _init_health_status(self):
        """初始化健康状态"""
        now = time.time()
        components = [
            "screenshot",
            "upload",
            "network",
            "heartbeat",
            "config",
            "watchdog",
            "power",
        ]

        for name in components:
            if name in self.health_monitor.components:
                self.health_monitor.components[name].last_check_time = now
                self.health_monitor.update_status(
                    name,
                    HealthStatus.HEALTHY,
                    "组件初始化完成",
                )

    # ===== 恢复回调 =====
    def _recover_screenshot(self):
        """截图组件恢复"""
        self.logger.info("🔄 恢复截图组件")
        if self.screenshot_manager:
            self.screenshot_manager.last_screenshot_path = None
        if self.watchdog:
            self.watchdog.heartbeat("screenshot")

    def _recover_upload(self):
        """上传组件恢复"""
        self.logger.info("🔄 恢复上传组件")
        if self.upload_queue and not self.offline_mode:
            threading.Thread(
                target=self.upload_queue._load_cached_tasks, daemon=True
            ).start()
        if self.watchdog:
            self.watchdog.heartbeat("upload")

    def _recover_network(self):
        """网络组件恢复"""
        self.logger.info("🔄 恢复网络组件")
        self.force_network_check = True
        if self.watchdog:
            self.watchdog.heartbeat("network")

    def _recover_heartbeat(self):
        """心跳组件恢复"""
        self.logger.info("🔄 恢复心跳组件")
        if self.watchdog:
            self.watchdog.heartbeat("heartbeat")

    def _recover_config(self):
        """配置组件恢复"""
        self.logger.info("🔄 恢复配置组件")
        self.config_manager.reload_if_changed()
        if self.watchdog:
            self.watchdog.heartbeat("config")

    def _recover_watchdog(self):
        """看门狗组件恢复"""
        self.logger.info("🔄 恢复看门狗组件")
        if self.watchdog and not self.watchdog.running:
            self.watchdog.start()
        if self.watchdog:
            self.watchdog.heartbeat("watchdog")

    # ===== 注册 =====
    def register_with_server(self, silent_mode: bool = False) -> bool:
        """向服务器注册（完美版）

        结合两个版本的优点：
        1. 简洁清晰的代码结构
        2. 统一的异常处理
        3. 正确的API调用
        4. 完善的日志
        """

        from client_config import Config
        import json

        # ===== 1. 强制使用配置文件服务器 =====
        self.server_urls = Config.DEFAULT_SERVERS.copy()
        self.current_server_index = 0
        self.current_server = self.server_urls[self.current_server_index]

        self.logger.info("=" * 60)
        self.logger.info("📋 服务器配置信息")
        self.logger.info("=" * 60)
        for i, server in enumerate(self.server_urls):
            self.logger.info(f"    {i+1}. {server}")
        self.logger.info(f"🎯 当前服务器: {self.current_server}")

        # ===== 2. 初始化或更新 APIClient =====
        if not self.api_client or self.api_client.base_url != self.current_server:
            self.api_client = APIClient(
                self.current_server,
                retry_times=self.retry_times,
                retry_delay=self.retry_delay,
            )
            self.logger.info(f"✅ API客户端已初始化: {self.current_server}")

        # ===== 3. 服务器健康检查（修复版）=====
        try:
            health_data = self.api_client.get("/health", timeout=3)
            if health_data:
                status = health_data.get("status")
                # 服务器返回 "healthy" 或 "ok" 都认为是健康的
                if status in ("healthy", "ok"):
                    self.logger.info(f"✅ 服务器健康检查通过")
                else:
                    self.logger.warning(f"⚠️ 服务器返回状态: {status}")
            else:
                self.logger.warning(f"⚠️ 服务器健康检查返回空数据")

        except Exception as e:
            self.logger.warning(f"⚠️ 服务器健康检查失败: {e}")
            self.logger.info("将继续尝试注册...")

        # ===== 4. 获取员工姓名（你的简洁版本）=====
        employee_name = None

        # 优先使用已有员工姓名
        if self.employee_name and not self._force_reconfigure:
            employee_name = self.employee_name
            self.logger.info(f"📝 使用已有员工姓名: {employee_name}")

        # 再尝试从配置文件读取
        if not employee_name:
            saved_name = self.config_manager.get("employee_name")
            if saved_name and not self._force_reconfigure:
                employee_name = saved_name
                self.logger.info(f"📝 从配置文件读取员工姓名: {employee_name}")

        # 最后弹GUI（只弹一次）
        if (
            not employee_name
            and not silent_mode
            and not getattr(self, "_gui_shown", False)
        ):
            try:
                from client_gui import get_employee_name_gui

                self.logger.info("🪟 弹出姓名输入对话框")
                gui_name = get_employee_name_gui()
                if gui_name:
                    employee_name = gui_name
                    self.logger.info(f"✅ 通过GUI获取员工姓名: {employee_name}")
                self._gui_shown = True
            except Exception as e:
                self.logger.error(f"❌ GUI启动失败: {e}")

        # 最后 fallback 到系统用户名
        if not employee_name:
            employee_name = self.system_info.get_windows_user() or "Employee"
            self.logger.info(f"💻 使用系统用户名: {employee_name}")

        # ===== 5. 收集硬件信息 =====
        self.logger.info("🔍 收集硬件信息...")
        system_info = self.system_info.get_system_info()
        hardware_info = self.system_info.get_hardware_fingerprint()

        self.logger.debug(f"💻 计算机名: {system_info.get('computer_name')}")
        self.logger.debug(f"🖥️  IP地址: {system_info.get('ip_address')}")
        self.logger.debug(f"🔑 硬件指纹: {hardware_info.get('hardware_fingerprint')}")

        # ===== 6. 构建注册数据 =====
        register_data = {
            "client_id": self.client_id or None,
            "computer_name": system_info.get("computer_name"),
            "windows_user": system_info.get("windows_user"),
            "mac_address": hardware_info.get("mac_address"),
            "ip_address": system_info.get("ip_address"),
            "os_version": system_info.get("os_version"),
            "cpu_id": hardware_info.get("cpu_id"),
            "disk_serial": hardware_info.get("disk_serial"),
            "client_version": self.version,
            "interval": self.interval,
            "quality": self.quality,
            "format": self.format,
            "employee_name": employee_name,
            "capabilities": ["webp", "heartbeat", "batch", "encryption"],
            "hardware_fingerprint": hardware_info.get("hardware_fingerprint"),
            "hardware_parts": hardware_info.get("hardware_parts"),
        }

        if self.security:
            register_data = self.security.sign_data(register_data)
            self.logger.debug("✅ 数据已签名")

        # ===== 7. 发送注册请求（统一异常处理）=====
        self.logger.info(
            f"📡 向服务器发送注册请求: {self.current_server}/api/client/register"
        )
        self.logger.debug(
            f"注册数据: {json.dumps(register_data, indent=2, ensure_ascii=False)}"
        )

        try:
            response = self.api_client.post("/api/client/register", json=register_data)
            if not response:
                raise Exception("服务器返回空数据")

            # 解析响应
            self.client_id = response.get("client_id")
            self.employee_id = response.get("employee_id")
            self.logger.info(
                f"✅ 注册成功! 客户端ID: {self.client_id}, 员工ID: {self.employee_id}"
            )

            if hasattr(self, "remote_screen") and self.remote_screen:
                self.logger.info("🔄 注册成功，正在启动远程屏幕服务...")

                # 更新配置
                self.remote_screen.config.client_id = self.client_id
                self.remote_screen.config.employee_id = self.employee_id
                self.remote_screen.config.server_url = self.current_server

                # 如果已经有挂起的启动请求，或者需要重新启动
                if (
                    hasattr(self.remote_screen, "_pending_start")
                    and self.remote_screen._pending_start
                ):
                    self.remote_screen._pending_start = False

                # 如果正在运行，先停止再重新启动
                if self.remote_screen.running:
                    self.logger.info("远程屏幕已在运行，重新连接...")
                    self.remote_screen.stop()
                    time.sleep(1)  # 等待完全停止

                # 启动远程屏幕
                self.remote_screen.start()
                self.logger.info("✅ 远程屏幕服务已启动")

            # 更新服务器配置
            if "config" in response:
                self._update_config_from_server(response["config"])
                self.logger.info("📋 已应用服务器配置")

            # 保存本地配置
            self.config_manager.update(
                client_id=self.client_id,
                employee_id=self.employee_id,
                interval=self.interval,
                quality=self.quality,
                format=self.format,
                employee_name=employee_name,
                version=self.version,
                server_urls=self.server_urls,
                enable_browser_monitor=self.enable_browser_monitor,
                enable_app_monitor=self.enable_app_monitor,
                enable_file_monitor=self.enable_file_monitor,
                enable_heartbeat=self.enable_heartbeat,
                enable_batch_upload=self.enable_batch_upload,
            )
            self.logger.info("💾 配置已保存到本地")

            # 重置状态
            self._force_reconfigure = False
            self.first_run = False
            self.offline_mode = False

            # 看门狗心跳
            if self.watchdog:
                self.watchdog.heartbeat("main")

            return True

        except Exception as e:
            self.logger.error(f"❌ 注册失败: {e}", exc_info=True)
            if not self.offline_mode:
                self.offline_mode = True
                self.logger.info("📴 进入离线模式")
            return False

    def _get_employee_name(self, silent_mode: bool) -> Optional[str]:
        """获取员工姓名（优化版 - 避免重复GUI）"""

        # 1. 已有姓名且不是强制重新配置
        if self.employee_name and not self._force_reconfigure:
            self.logger.debug(f"使用已有姓名: {self.employee_name}")
            return self.employee_name

        # 2. 从配置读取
        saved_name = self.config_manager.get("employee_name")
        if saved_name and not self._force_reconfigure:
            self.logger.debug(f"从配置读取姓名: {saved_name}")
            return saved_name

        # 3. 静默模式 - 使用默认
        if silent_mode:
            default_name = self.system_info.get_windows_user() or "Employee"
            self.logger.debug(f"静默模式使用默认: {default_name}")
            return default_name

        # 4. 已经弹过GUI了，不再重复弹出
        if hasattr(self, "_gui_shown") and self._gui_shown:
            default_name = self.system_info.get_windows_user() or "Employee"
            self.logger.debug(f"GUI已弹出过，使用默认: {default_name}")
            return default_name

        # 5. 弹出GUI获取
        try:
            from client_gui import get_employee_name_gui

            self.logger.info("弹出姓名输入对话框")
            gui_name = get_employee_name_gui()
            if gui_name:
                self._gui_shown = True
                return gui_name
        except Exception as e:
            self.logger.error(f"GUI启动失败: {e}")

        # 6. 最终fallback
        return self.system_info.get_windows_user() or "Employee"

    def _update_config_from_server(self, config: Dict):
        """从服务器更新配置"""
        changed = False

        # 截图间隔
        if config.get("interval") and config["interval"] != self.interval:
            self.interval = config["interval"]
            changed = True
            self.logger.info(f"📋 截图间隔更新: {self.interval}秒")

        # 图片质量
        if config.get("quality") and config["quality"] != self.quality:
            self.quality = config["quality"]
            if self.screenshot_manager:
                self.screenshot_manager.quality = self.quality
            changed = True

        # 图片格式
        if config.get("format") and config["format"] != self.format:
            self.format = config["format"]
            if self.screenshot_manager:
                self.screenshot_manager.format = self.format
            changed = True

        # 心跳开关
        if config.get("enable_heartbeat") is not None:
            self.enable_heartbeat = config["enable_heartbeat"]
            changed = True

        # 批量上传开关
        if config.get("enable_batch_upload") is not None:
            self.enable_batch_upload = config["enable_batch_upload"]
            changed = True

        # 相似度阈值
        if config.get("similarity_threshold") is not None:
            self.similarity_threshold = config["similarity_threshold"]
            if self.phash_detector:
                self.phash_detector.threshold = self.similarity_threshold
            changed = True

        # 重试次数
        if config.get("retry_times") is not None:
            self.retry_times = config["retry_times"]
            changed = True

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

            if self.watchdog:
                self.watchdog.heartbeat("config")

    # ===== 核心功能 =====
    def _take_screenshot_async(
        self, last_screenshot_path: Optional[str]
    ) -> Optional[str]:
        """异步执行截图（在工作线程中运行）"""
        try:
            # 频率限制
            now = time.time()
            if now - self._last_screenshot_time < self._min_screenshot_interval:
                self.logger.debug("截图太频繁，跳过")
                return None

            # 截图
            screenshot = self.multi_monitor.capture_all_monitors()
            if not screenshot:
                self.logger.error("截图失败")
                return None

            # 保存到临时文件
            buffer = get_buffer()
            temp_path = None

            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.{self.format}"
                filepath = os.path.join(os.getcwd(), filename)

                # 创建临时文件
                fd, temp_path = tempfile.mkstemp(
                    suffix=f".{self.format}", prefix=".tmp_"
                )
                os.close(fd)

                # 保存图片
                if self.format == "webp":
                    screenshot.save(
                        temp_path, "WEBP", quality=self.quality, optimize=True, method=6
                    )
                else:
                    screenshot.save(
                        temp_path, "JPEG", quality=self.quality, optimize=True
                    )

                # 原子重命名
                shutil.move(temp_path, filepath)
                temp_path = None  # 避免后续清理

                self._last_screenshot_time = time.time()

                with self._stats_lock:
                    self._stats["screenshots_taken"] += 1

                # 健康状态更新
                if self.health_monitor:
                    self.health_monitor.update_status(
                        "screenshot",
                        HealthStatus.HEALTHY,
                        f"截图成功",
                    )

                # 相似度检测
                if last_screenshot_path and os.path.exists(last_screenshot_path):
                    if self.phash_detector.are_similar(last_screenshot_path, filepath):
                        self.logger.debug("屏幕内容无变化，删除截图")

                        # 删除文件
                        try:
                            os.unlink(filepath)
                        except:
                            pass

                        with self._stats_lock:
                            self._stats["skipped_similar"] += 1

                        return None

                # 创建上传任务
                with open(filepath, "rb") as f:
                    image_data = f.read()

                # 加密
                if self.security and self.encryption_enabled:
                    image_data = self.security.encrypt_data(image_data)

                task = UploadTask(
                    image_data=image_data,
                    filename=os.path.basename(filepath),
                    employee_id=self.employee_id,
                    client_id=self.client_id,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    computer_name=self.system_info.get_computer_name(),
                    windows_user=self.system_info.get_windows_user(),
                    format=self.format,
                    encrypted=self.encryption_enabled,
                )

                # 入队
                if self.upload_queue and self.upload_queue.enqueue(task):
                    # 删除原始文件
                    try:
                        os.unlink(filepath)
                    except:
                        pass

                    if self.health_monitor:
                        self.health_monitor.update_status(
                            "upload", HealthStatus.HEALTHY
                        )

                    if self.watchdog:
                        self.watchdog.heartbeat("upload")

                    return filepath
                else:
                    self.logger.warning("上传队列已满，保留本地文件")
                    return filepath

            finally:
                put_buffer(buffer)
                # 清理临时文件
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

        except Exception as e:
            self.logger.error(f"截图处理异常: {e}", exc_info=True)

            if self.error_recovery:
                self.error_recovery.report_error(e, "screenshot")

            return None

    def _work_loop(self):
        """主工作循环"""
        self.logger.info(f"🚀 开始监控，间隔: {self.interval}秒")

        # 状态变量
        last_screenshot_time = 0
        last_screenshot_path = None
        last_sync_time = 0
        consecutive_failures = 0

        # 线程池
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)

        # 计算首次截图时间
        now = time.time()
        next_screenshot = math.ceil(now / self.interval) * self.interval

        while self.running:
            try:
                now = time.time()

                # 看门狗心跳
                if self.watchdog:
                    self.watchdog.heartbeat("main")

                # 暂停处理
                if self.paused:
                    time.sleep(2)
                    continue

                # ===== 立即截图 =====
                if self.take_screenshot_now:
                    self.take_screenshot_now = False

                    if now - last_screenshot_time >= self._min_screenshot_interval:
                        future = executor.submit(
                            self._take_screenshot_async, last_screenshot_path
                        )
                        try:
                            path = future.result(timeout=15)
                            if path:
                                last_screenshot_path = path
                                last_screenshot_time = now
                                consecutive_failures = 0
                            else:
                                consecutive_failures += 1
                        except Exception as e:
                            self.logger.error(f"立即截图失败: {e}")
                            consecutive_failures += 1

                    next_screenshot = max(next_screenshot, now + self.interval)
                    time.sleep(0.2)
                    continue

                # ===== 定时截图 =====
                if now >= next_screenshot:
                    if now - last_screenshot_time >= self._min_screenshot_interval:
                        future = executor.submit(
                            self._take_screenshot_async, last_screenshot_path
                        )
                        try:
                            path = future.result(timeout=15)
                            if path:
                                last_screenshot_path = path
                                last_screenshot_time = now
                                consecutive_failures = 0
                            else:
                                consecutive_failures += 1
                        except Exception as e:
                            self.logger.error(f"定时截图失败: {e}")
                            consecutive_failures += 1

                    next_screenshot += self.interval

                # ===== 配置同步（10分钟）=====
                if (
                    now - last_sync_time >= 600
                    and not self.offline_mode
                    and self.api_client
                ):
                    try:
                        config = self.api_client.get(
                            f"/api/client/{self.client_id}/config"
                        )
                        if config:
                            self._update_config_from_server(config)
                    except Exception as e:
                        self.logger.debug(f"配置同步失败: {e}")

                    last_sync_time = now

                # ===== 智能休眠 =====
                time_to_next = next_screenshot - time.time()

                if time_to_next > 10:
                    time.sleep(min(3, time_to_next - 5))
                elif time_to_next > 3:
                    time.sleep(1)
                elif time_to_next > 0:
                    time.sleep(0.2)
                else:
                    time.sleep(0.05)

            except Exception as e:
                self.logger.error(f"工作循环异常: {e}", exc_info=True)

                if self.error_recovery:
                    self.error_recovery.report_error(e, "main_loop")

                time.sleep(5)

        executor.shutdown(wait=False)

    def _heartbeat_sender(self):
        """心跳发送线程"""
        while self.running:
            try:
                if not self.offline_mode and self.enable_heartbeat and self.api_client:
                    self.send_heartbeat()
            except Exception as e:
                self.logger.debug(f"心跳异常: {e}")

            # 休眠60秒
            for _ in range(60):
                if not self.running:
                    return
                time.sleep(1)

    def send_heartbeat(self) -> bool:
        """发送心跳"""
        if not self.api_client or not self.client_id:
            return False

        try:
            start = time.time()

            # 收集数据
            stats = (
                self.system_info.get_system_stats()
                if hasattr(self.system_info, "get_system_stats")
                else {}
            )
            queue_stats = self.upload_queue.get_stats() if self.upload_queue else {}
            health_summary = (
                self.health_monitor.get_summary() if self.health_monitor else {}
            )
            power_stats = self.power_manager.get_stats() if self.power_manager else {}
            error_stats = self.error_recovery.get_stats() if self.error_recovery else {}

            heartbeat_data = {
                "status": "online",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stats": stats,
                "client_stats": self.get_stats(),
                "queue_stats": queue_stats,
                "health_summary": health_summary,
                "power_stats": power_stats,
                "error_stats": error_stats,
                "paused": self.paused,
                "offline_mode": self.offline_mode,
                "ip_address": self.system_info.get_ip_address(),
            }

            # 添加签名
            if self.security:
                heartbeat_data = self.security.sign_data(heartbeat_data)

            response = self.api_client.post(
                f"/api/client/{self.client_id}/heartbeat",
                json=heartbeat_data,
                timeout=10,
            )

            response_time = (time.time() - start) * 1000

            if response:
                with self._stats_lock:
                    self._stats["last_heartbeat"] = time.time()

                if self.health_monitor:
                    self.health_monitor.update_status(
                        "heartbeat",
                        HealthStatus.HEALTHY,
                        f"延迟: {response_time:.0f}ms",
                        response_time=response_time,
                    )

                if self.watchdog:
                    self.watchdog.heartbeat("heartbeat")

                self.logger.debug(f"❤️ 心跳成功 ({response_time:.0f}ms)")
                return True

        except Exception as e:
            self.logger.debug(f"心跳失败: {e}")

            if self.error_recovery:
                self.error_recovery.report_error(e, "heartbeat")

            if self.health_monitor:
                self.health_monitor.update_status(
                    "heartbeat", HealthStatus.DEGRADED, str(e)
                )

        return False

    def _network_monitor(self):
        """网络监控线程"""
        import socket

        session = requests.Session()
        check_interval = 20
        consecutive_failures = 0

        while self.running:
            try:
                now = time.time()

                # 基础网络检测
                if not self._check_basic_network():
                    if not self.offline_mode:
                        self.logger.warning("⚠️ 网络不可用")
                        self.offline_mode = True
                    time.sleep(10)
                    continue

                # 服务器检测
                current_server = self.server_urls[self.current_server_index]

                try:
                    response = session.get(
                        f"{current_server}/health",
                        timeout=5,
                        verify=False,
                    )

                    if response.status_code == 200:
                        if self.offline_mode:
                            self.logger.info("🌐 网络恢复")
                            self.offline_mode = False

                            # 重新注册
                            threading.Thread(
                                target=self.register_with_server, daemon=True
                            ).start()

                        self.current_server = current_server
                        consecutive_failures = 0
                        check_interval = 20

                        if self.api_client:
                            self.api_client.base_url = current_server

                    else:
                        raise Exception(f"HTTP {response.status_code}")

                except Exception as e:
                    consecutive_failures += 1
                    self.logger.debug(f"服务器检测失败: {e}")

                    # 切换服务器
                    if consecutive_failures >= 3:
                        self._switch_server()
                        consecutive_failures = 0

                # 动态调整检查间隔
                if consecutive_failures > 0:
                    check_interval = min(check_interval * 1.5, 120)

                time.sleep(min(check_interval, 60))

            except Exception as e:
                self.logger.error(f"网络监控异常: {e}")
                time.sleep(30)

    def _check_basic_network(self) -> bool:
        """检查基础网络"""
        try:
            socket.create_connection(("8.8.8.8", 53), 3)
            return True
        except:
            return False

    def _switch_server(self):
        """切换服务器"""
        old_index = self.current_server_index
        self.current_server_index = (self.current_server_index + 1) % len(
            self.server_urls
        )
        new_server = self.server_urls[self.current_server_index]

        self.logger.info(
            f"🔄 切换服务器: {old_index} → {self.current_server_index} ({new_server})"
        )

        self.current_server = new_server
        if self.api_client:
            self.api_client.base_url = new_server

    def _batch_uploader(self):
        """批量上传线程"""
        while self.running:
            time.sleep(1800)  # 30分钟

            if self.running and not self.offline_mode and self.enable_batch_upload:
                try:
                    self._upload_screenshots_batch()
                except Exception as e:
                    self.logger.error(f"批量上传失败: {e}")

    def _upload_screenshots_batch(self) -> bool:
        """批量上传截图"""
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
                    screenshots.append(str(file))

            if not screenshots:
                return False

            self.logger.info(f"📦 批量上传 {len(screenshots)} 个截图")

            # 创建ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for screenshot in screenshots:
                    with open(screenshot, "rb") as f:
                        zip_file.writestr(os.path.basename(screenshot), f.read())

            # 上传
            files = {
                "batch": ("screenshots.zip", zip_buffer.getvalue(), "application/zip")
            }
            data = {
                "client_id": self.client_id,
                "employee_id": self.employee_id,
                "count": len(screenshots),
            }

            response = self.api_client.session.post(
                f"{self.current_server}/api/upload/batch",
                files=files,
                data=data,
                timeout=120,
            )

            if response.status_code == 200:
                # 删除本地文件
                deleted = 0
                for screenshot in screenshots:
                    try:
                        os.remove(screenshot)
                        deleted += 1
                    except:
                        pass

                with self._stats_lock:
                    self._stats["screenshots_uploaded"] += len(screenshots)
                    self._stats["last_upload_time"] = time.time()

                self.logger.info(f"✅ 批量上传成功 ({deleted}/{len(screenshots)})")
                return True

        except Exception as e:
            self.logger.error(f"批量上传失败: {e}")

        return False

    # ===== 公共API =====
    def upload_screenshot(self, image_path: str) -> bool:
        """上传截图（兼容旧接口）"""
        if self.offline_mode:
            return False

        if not os.path.exists(image_path):
            return False

        try:
            with open(image_path, "rb") as f:
                files = {
                    "file": (os.path.basename(image_path), f, f"image/{self.format}")
                }

                data = {
                    "employee_id": self.employee_id,
                    "client_id": self.client_id,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "computer_name": self.system_info.get_computer_name(),
                    "windows_user": self.system_info.get_windows_user(),
                    "encrypted": str(self.encryption_enabled).lower(),
                    "format": self.format,
                }

                response = self.api_client.session.post(
                    f"{self.current_server}/api/upload",
                    files=files,
                    data=data,
                    timeout=60,
                )

            if response.status_code == 200:
                with self._stats_lock:
                    self._stats["screenshots_uploaded"] += 1
                    self._stats["last_upload_time"] = time.time()

                try:
                    os.remove(image_path)
                except:
                    pass

                return True

        except Exception as e:
            self.logger.error(f"上传失败: {e}")
            with self._stats_lock:
                self._stats["upload_failures"] += 1

        return False

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._stats_lock:
            stats = self._stats.copy()

            if stats["start_time"]:
                stats["uptime"] = time.time() - stats["start_time"]

            # 添加子系统统计
            if self.upload_queue:
                stats["queue"] = self.upload_queue.get_stats()

            if self.health_monitor:
                stats["health"] = self.health_monitor.get_summary()

            if self.watchdog:
                stats["watchdog"] = self.watchdog.get_status()

            if self.power_manager:
                stats["power"] = self.power_manager.get_stats()

            if self.error_recovery:
                stats["error_recovery"] = self.error_recovery.get_stats()

            if self.security:
                stats["security"] = self.security.get_stats()

            return stats

    # ===== 生命周期 =====
    def start(self, silent_mode: bool = False):
        """启动监控"""
        self.logger.info("=" * 60)
        self.logger.info(f"员工监控系统客户端 v{self.version} (企业版)")
        self.logger.info("=" * 60)

        # 初始化子系统
        self._init_subsystems()

        # 启动健康监控
        self.health_monitor.start_monitoring()

        # 启动错误恢复系统
        self.error_recovery.start()

        # 启动上传队列
        self.upload_queue.start()

        # 启动功耗管理
        self.power_manager.start()

        # 启动看门狗
        self.watchdog.start()

        # 注册到服务器
        if not self.register_with_server(silent_mode=silent_mode):
            self.logger.warning("注册失败，将以离线模式运行")
            self.offline_mode = True

        self.running = True
        self._stats["start_time"] = time.time()

        # 注册线程
        self._start_thread("work_loop", self._work_loop)
        self._start_thread("network_monitor", self._network_monitor)

        if self.enable_heartbeat:
            self._start_thread("heartbeat_sender", self._heartbeat_sender)

        if self.enable_batch_upload:
            self._start_thread("batch_uploader", self._batch_uploader)

        # ===== 启动新增监控 =====
        if self.browser_monitor:
            self.browser_monitor.start_monitoring()

        if self.app_monitor:
            self.app_monitor.start_monitoring()

        if self.file_monitor:
            self.file_monitor.start_monitoring()

        if self.remote_screen:
            self.remote_screen.start()

        self.logger.info("✅ 监控程序启动成功")

        # 托盘图标
        self._init_tray_icon()

    def _start_thread(self, name: str, target: callable):
        """启动线程"""
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        with self._thread_lock:
            self._threads.append(thread)
        self.logger.debug(f"线程已启动: {name}")

    def _init_tray_icon(self):
        """初始化托盘图标"""
        try:
            # 尝试导入托盘图标
            from client_tray import EnhancedTrayIcon

            self.tray = EnhancedTrayIcon(self)
            tray_thread = threading.Thread(
                target=self.tray.run, name="TrayIcon", daemon=True
            )
            tray_thread.start()
            self.logger.info("✅ 托盘图标已启动")
        except ImportError:
            self.logger.warning("⚠️ 托盘图标功能不可用")

        # 主循环
        try:
            while self.running:
                time.sleep(1)
                if self.tray and hasattr(self.tray, "update_icon_title"):
                    self.tray.update_icon_title()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """停止监控"""
        self.logger.info("⏹️ 正在停止监控程序...")
        self.running = False

        # 停止看门狗
        if self.watchdog:
            self.watchdog.stop()

        # 停止功耗管理
        if self.power_manager:
            self.power_manager.stop()

        # 停止上传队列
        if self.upload_queue:
            self.upload_queue.stop()

        # 停止健康监控
        if self.health_monitor:
            self.health_monitor.stop_monitoring()

        if self.file_monitor:
            self.file_monitor.stop_monitoring()

        if self.remote_screen:
            self.remote_screen.stop()

        # 最后的心跳
        if not self.offline_mode and self.enable_heartbeat:
            self.send_heartbeat()

        # 打印统计
        uptime = time.time() - self._stats["start_time"]
        self.logger.info("=" * 60)
        self.logger.info(f"📊 运行统计")
        self.logger.info(f"⏱️  运行时间: {uptime/3600:.2f}小时")
        self.logger.info(f"📸 截图数量: {self._stats['screenshots_taken']}")
        self.logger.info(f"⏭️  跳过相似: {self._stats.get('skipped_similar', 0)}")
        self.logger.info(f"✅ 上传成功: {self._stats['screenshots_uploaded']}")
        self.logger.info(f"❌ 上传失败: {self._stats['upload_failures']}")

        if self.power_manager:
            power_stats = self.power_manager.get_stats()
            self.logger.info(
                f"🔋 节电时间: {power_stats.get('total_time_saved', 0)/3600:.2f}小时"
            )

        self.logger.info("=" * 60)

    # ===== 测试模式 =====
    def test_mode(self):
        """测试模式"""
        print("\n" + "=" * 60)
        print("🔧 测试模式 - 立即截图并上传")
        print("=" * 60)

        # 初始化子系统
        self._init_subsystems()

        # 注册
        if not self.register_with_server():
            self.logger.error("注册失败")
            return

        print(f"📋 客户端ID: {self.client_id}")
        print(f"📋 员工ID: {self.employee_id}")
        print(f"🌐 服务器: {self.current_server}")
        print("-" * 60)

        print("📸 正在截图...")
        last_screenshot_path = None
        path = self._take_screenshot_async(last_screenshot_path)

        if path:
            print(f"✅ 截图成功: {os.path.basename(path)}")
            print(f"📦 文件大小: {os.path.getsize(path)/1024:.1f}KB")
            print("📤 正在上传...")

            if self.upload_screenshot(path):
                print("✅ 上传成功")
            else:
                print("❌ 上传失败")
        else:
            print("❌ 截图失败")

        print("=" * 60)


# ========== ScreenshotManager 类（保留）==========
class ScreenshotManager:
    """截图管理器"""

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
        self.logger = logging.getLogger(__name__)

        self.last_screenshot_path = None
        self.screenshot_history = []
        self.stats = {"taken": 0, "uploaded": 0, "skipped": 0, "failed": 0}

        if self.format not in ["webp", "jpg", "jpeg"]:
            self.logger.warning(f"不支持的图片格式 {self.format}，使用 webp")
            self.format = "webp"

    def take_screenshot(self) -> Optional[str]:
        """截取屏幕"""
        try:
            multi_monitor = MultiMonitorScreenshot()
            screenshot = multi_monitor.capture_all_monitors()

            if not screenshot:
                screenshot = ImageGrab.grab(all_screens=True)

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

                AtomicFileOperation.atomic_write(filepath, buffer.getvalue())

                # 更新历史
                self.screenshot_history.append(filepath)
                if len(self.screenshot_history) > self.max_history:
                    old_file = self.screenshot_history.pop(0)
                    if old_file != self.last_screenshot_path:
                        try:
                            AtomicFileOperation.atomic_delete(old_file)
                        except:
                            pass

                self.stats["taken"] += 1
                file_size = os.path.getsize(filepath)
                self.logger.info(f"✅ 截图成功: {filename} ({file_size/1024:.1f}KB)")

                return filepath

            finally:
                put_buffer(buffer)

        except Exception as e:
            self.logger.error(f"❌ 截图失败: {e}")
            return None

    def are_similar(self, img1_path: str, img2_path: str) -> bool:
        """判断两张图片是否相似"""
        phash = PerceptualHash(threshold=self.similarity_threshold)
        similar = phash.are_similar(img1_path, img2_path)

        if similar:
            self.stats["skipped"] += 1

        return similar

    def cleanup_old_screenshots(self, max_age_hours: int = 24):
        """清理旧截图"""
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
                    f"🧹 清理了 {count} 个旧截图，释放 {size_freed/1024/1024:.2f}MB"
                )

        except Exception as e:
            self.logger.error(f"清理旧截图失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return self.stats.copy()


# ========== 主函数 ==========
def main():
    """主函数"""
    # 单实例检查
    if not _instance_lock.acquire("employee_monitor"):
        print("❌ 程序退出：已有实例在运行")
        return 1

    # 配置日志
    setup_logging(log_level=logging.INFO, log_file="monitor.log")
    logger = logging.getLogger(__name__)

    # 解析参数
    parser = argparse.ArgumentParser(
        description="员工监控系统客户端 - 企业版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-c", "--config", default="config.json", help="配置文件路径")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--register", action="store_true", help="仅注册")
    parser.add_argument("--reconfigure", action="store_true", help="强制重新配置")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )
    parser.add_argument("--server", action="append", help="指定服务器地址")
    parser.add_argument("--interval", type=int, help="截图间隔")
    parser.add_argument("--quality", type=int, choices=range(10, 101), help="图片质量")
    parser.add_argument("--format", choices=["webp", "jpg", "jpeg"], help="图片格式")
    parser.add_argument("--encrypt", action="store_true", help="启用加密")
    parser.add_argument("--silent", action="store_true", help="静默模式")
    parser.add_argument(
        "--version", action="version", version=f"员工监控系统客户端 {__version__}"
    )

    args = parser.parse_args()

    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # 创建客户端
    client = MonitorClient(args.config, force_reconfigure=args.reconfigure)

    # 命令行参数覆盖
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

    # 执行模式
    try:
        if args.test:
            client.test_mode()
        elif args.register:
            client.register_with_server(silent_mode=args.silent)
        else:
            client.start(silent_mode=args.silent)
    except KeyboardInterrupt:
        print("\n👋 程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
        return 1
    finally:
        _instance_lock.release()

    return 0


if __name__ == "__main__":
    sys.exit(main())
