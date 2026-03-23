#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件操作监控模块
- 监控文件的创建、修改、删除
- 使用 watchdog 库
"""

import os
import time
import logging
import threading
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class FileMonitorHandler(FileSystemEventHandler):
    """文件监控处理器"""

    def __init__(self, monitor):
        self.monitor = monitor
        self.logger = logging.getLogger(__name__)

        # 监控的目录
        user_home = os.path.expanduser("~")
        self.watch_dirs = [
            os.path.join(user_home, "Desktop"),  # 桌面
            os.path.join(user_home, "Documents"),  # 文档
            os.path.join(user_home, "Downloads"),  # 下载
            os.path.join(user_home, "Pictures"),  # 图片
            os.path.join(user_home, "Videos"),  # 视频
            os.path.join(user_home, "Music"),  # 音乐
        ]

        self.watch_dirs = [d for d in self.watch_dirs if os.path.exists(d)]

        self.ignore_dirs = [
            r"C:\Windows",
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            r"C:\Users\All Users",
            os.path.join(user_home, "AppData"),  # AppData 目录
            os.path.join(user_home, "Application Data"),
            os.path.join(user_home, "Local Settings"),
            os.path.join(user_home, "Cookies"),
            os.path.join(user_home, "NTUSER.DAT"),
        ]

        # 忽略的扩展名
        self.ignore_extensions = [".tmp", ".temp", ".log", ".cache", ".bak", ".lnk"]

        # 操作队列
        self.operations = []
        self.lock = threading.RLock()

    def should_ignore(self, path: str) -> bool:
        """是否应该忽略 - 只记录用户主动操作的文件"""
        path_lower = path.lower()

        # ✅ 1. 检查是否在忽略目录中
        for ignore_dir in self.ignore_dirs:
            if path_lower.startswith(ignore_dir.lower()):
                return True

        # ✅ 2. 忽略临时文件
        for ext in self.ignore_extensions:
            if path_lower.endswith(ext):
                return True

        # ✅ 3. 忽略隐藏文件（Windows）
        if os.path.basename(path).startswith(".") or os.path.basename(path).startswith(
            "~"
        ):
            return True

        # ✅ 4. 忽略零字节文件和空目录操作
        if os.path.exists(path):
            try:
                if os.path.getsize(path) == 0:
                    return True
            except:
                pass

        # ✅ 5. 忽略系统文件属性
        if sys.platform == "win32":
            try:
                import ctypes

                # 检查文件属性
                attributes = ctypes.windll.kernel32.GetFileAttributesW(path)
                if attributes & 0x2:  # FILE_ATTRIBUTE_HIDDEN
                    return True
                if attributes & 0x4:  # FILE_ATTRIBUTE_SYSTEM
                    return True
            except:
                pass

        return False

    def on_created(self, event):
        if event.is_directory:
            return
        if self.should_ignore(event.src_path):
            return

        with self.lock:
            self.operations.append(
                {
                    "operation": "create",
                    "file_path": event.src_path,
                    "file_name": os.path.basename(event.src_path),
                    "file_type": os.path.splitext(event.src_path)[1],
                    "is_directory": event.is_directory,
                    "timestamp": time.time(),
                }
            )

    def on_modified(self, event):
        if event.is_directory:
            return
        if self.should_ignore(event.src_path):
            return

        with self.lock:
            self.operations.append(
                {
                    "operation": "modify",
                    "file_path": event.src_path,
                    "file_name": os.path.basename(event.src_path),
                    "file_type": os.path.splitext(event.src_path)[1],
                    "is_directory": event.is_directory,
                    "timestamp": time.time(),
                }
            )

    def on_deleted(self, event):
        if event.is_directory:
            return
        if self.should_ignore(event.src_path):
            return

        with self.lock:
            self.operations.append(
                {
                    "operation": "delete",
                    "file_path": event.src_path,
                    "file_name": os.path.basename(event.src_path),
                    "file_type": os.path.splitext(event.src_path)[1],
                    "is_directory": event.is_directory,
                    "timestamp": time.time(),
                }
            )

    def on_moved(self, event):
        if event.is_directory:
            return

        with self.lock:
            # 原文件删除
            self.operations.append(
                {
                    "operation": "delete",
                    "file_path": event.src_path,
                    "file_name": os.path.basename(event.src_path),
                    "file_type": os.path.splitext(event.src_path)[1],
                    "is_directory": event.is_directory,
                    "timestamp": time.time(),
                }
            )

            # 新文件创建
            self.operations.append(
                {
                    "operation": "create",
                    "file_path": event.dest_path,
                    "file_name": os.path.basename(event.dest_path),
                    "file_type": os.path.splitext(event.dest_path)[1],
                    "is_directory": event.is_directory,
                    "timestamp": time.time(),
                }
            )


class FileMonitor:
    """文件监控器"""

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        self.handler = FileMonitorHandler(self)
        self.observer = None
        self.running = False

        # 上报间隔
        self.report_interval = 60  # 1分钟
        self.last_report_time = time.time()

    def start_monitoring(self):
        """启动文件监控"""
        if not WATCHDOG_AVAILABLE:
            self.logger.warning("⚠️ watchdog未安装，文件监控不可用")
            return

        try:
            self.observer = Observer()
            for watch_dir in self.handler.watch_dirs:
                if os.path.exists(watch_dir):
                    self.observer.schedule(self.handler, watch_dir, recursive=True)
                    self.logger.info(f"监控目录: {watch_dir}")

            self.observer.start()
            self.running = True
            self.logger.info("✅ 文件监控已启动")

            # 启动上报线程
            threading.Thread(target=self._report_loop, daemon=True).start()

        except Exception as e:
            self.logger.error(f"启动文件监控失败: {e}")

    def _report_loop(self):
        """上报循环"""
        while self.running and self.client.running:
            try:
                self.collect_and_report()
                time.sleep(10)
            except Exception as e:
                self.logger.error(f"文件监控上报异常: {e}")
                time.sleep(30)

    def collect_and_report(self):
        """收集并上报文件操作"""
        current_time = time.time()

        if current_time - self.last_report_time < self.report_interval:
            return

        with self.handler.lock:
            operations = self.handler.operations.copy()
            self.handler.operations.clear()

        if not operations or not self.client.employee_id:
            return

        # ✅ 过滤掉无效操作
        valid_operations = []
        for op in operations:
            # 确保是文件操作（不是目录）
            if op.get("is_directory"):
                continue

            # 获取文件大小
            if op["operation"] != "delete" and os.path.exists(op["file_path"]):
                try:
                    op["file_size"] = os.path.getsize(op["file_path"])
                    # ✅ 忽略空文件
                    if op["file_size"] == 0:
                        continue
                except:
                    op["file_size"] = 0
            else:
                op["file_size"] = 0

            # ✅ 添加必需的字段
            op["employee_id"] = self.client.employee_id
            op["client_id"] = self.client.client_id
            op["operation_time"] = datetime.fromtimestamp(op["timestamp"]).isoformat()

            # 删除临时字段
            del op["timestamp"]

            valid_operations.append(op)

        if not valid_operations:
            return

        self.logger.info(f"收集到 {len(valid_operations)} 条文件操作（过滤后）")

        # 上报
        if self.client.api_client and not self.client.offline_mode:
            try:
                # 注意：这里假设 api_client.post 已实现或使用 requests 等库
                response = self.client.api_client.post(
                    "/api/files/operations", json=valid_operations
                )
                if response:
                    self.logger.info(f"✅ 文件操作上报成功: {len(valid_operations)}条")
                    self.last_report_time = current_time
                else:
                    self._save_to_cache(valid_operations)
            except Exception as e:
                self.logger.error(f"上报文件操作失败: {e}")
                self._save_to_cache(valid_operations)
        else:
            self._save_to_cache(valid_operations)

    def _save_to_cache(self, operations: List[Dict]):
        """保存到缓存"""
        cache_file = Path("cache") / f"files_{int(time.time())}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(operations, f)
        except Exception as e:
            self.logger.error(f"缓存文件操作失败: {e}")

    def stop_monitoring(self):
        """停止文件监控"""
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.logger.info("⏹️ 文件监控已停止")
