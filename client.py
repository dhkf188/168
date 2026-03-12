#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工监控系统客户端 - 完整增强版
功能：
1. 自动注册客户端（支持多服务器检测）
2. 定时截图上传（WebP/JPG格式支持）
3. 系统托盘图标管理
4. 开机自启动管理
5. 配置自动生成和动态加载
6. 心跳保活机制
7. 批量上传支持
8. 图片相似度检测
9. 加密支持
10. 系统信息收集
11. 配置文件监控
12. 错误重试机制
13. 离线模式支持
14. 网络状态自动检测
15. 多服务器故障转移
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps

# 第三方库导入
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

# 配置日志
logger = setup_logging()


class MonitorClient:
    """监控客户端主类"""

    def __init__(self, config_file="config.json"):
        # 初始化组件
        self.config_manager = ConfigManager(config_file)
        self.system_info = SystemInfoCollector()
        self.api_client = None
        self.tray = None

        self.first_run = False

        self.CURRENT_VERSION = "3.0.1"
        self._check_and_reset_old_config()

        self.force_network_check = False

        # 从配置加载设置
        self._load_config()

        if not self.client_id:
            self.first_run = True
            logger.info("🔔 检测到首次运行，将启动设置向导")

        # 初始化截图管理器
        self.screenshot_manager = ScreenshotManager(
            quality=self.quality,
            format=self.format,
            max_history=self.max_history,
            similarity_threshold=self.similarity_threshold,
            encryption_key=os.environ.get("ENCRYPTION_KEY"),
        )

        # 状态变量
        self.running = False
        self.paused = False
        self.take_screenshot_now = False
        self.offline_mode = False
        self.current_server_index = 0

        self.ws_manager = None
        self.enable_websocket = self.config_manager.get("enable_websocket", True)

        # 统计信息
        self.stats = {
            "screenshots_taken": 0,
            "screenshots_uploaded": 0,
            "upload_failures": 0,
            "start_time": None,
            "last_upload_time": None,
            "last_heartbeat": None,
            "errors": [],
        }

        # 线程锁
        self.stats_lock = threading.RLock()
        self.error_lock = threading.RLock()

        # 尝试创建托盘图标
        try:
            from pystray import Icon

            self.tray = TrayIcon(self)
            logger.info("✅ 托盘图标已创建")
        except ImportError:
            logger.warning("⚠️ pystray未安装，托盘图标功能不可用")
            self.tray = None
        except Exception as e:
            logger.error(f"❌ 创建托盘图标失败: {e}")
            self.tray = None

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

        logger.info(
            f"📝 初始配置 - 间隔: {self.interval}秒, 质量: {self.quality}, 格式: {self.format}"
        )

    def _check_and_reset_old_config(self):
        """
        检查是否需要重置旧配置
        当代码更新或服务器变更时自动重置
        """
        try:
            config_file = Path("config.json")
            if not config_file.exists():
                return

            # 读取现有配置
            with open(config_file, "r", encoding="utf-8") as f:
                old_config = json.load(f)

            # ===== 检测条件1：配置中没有版本号 =====
            old_version = old_config.get("version")

            # ===== 检测条件2：配置中有旧的client_id但服务器可能已重置 =====
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

            # ===== 检测条件3：检查服务器状态 =====
            if not need_reset and old_config.get("client_id"):
                try:
                    # 尝试连接服务器验证client_id
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

            # ===== 如果需要重置，自动备份并删除 =====
            if need_reset:
                logger.warning(f"🔄 检测到需要重置配置: {', '.join(reset_reason)}")

                # 创建备份目录
                backup_dir = Path("backup")
                backup_dir.mkdir(exist_ok=True)

                # 备份旧配置
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = backup_dir / f"config_backup_{timestamp}.json"

                import shutil

                shutil.copy2(config_file, backup_file)
                logger.info(f"📦 旧配置已备份到: {backup_file}")

                # 删除旧配置
                config_file.unlink()
                logger.info("🗑️ 旧配置已删除")

                # 重置内存中的配置
                self.config_manager.config = self.config_manager.DEFAULT_CONFIG.copy()
                self.config_manager.save()

                logger.info("✅ 配置重置完成，将使用新配置")

        except Exception as e:
            logger.error(f"检查旧配置时出错: {e}")

    def validate_config(self):
        """验证配置有效性"""
        if not self.server_urls:
            logger.error("未配置服务器地址")
            return False

        # 验证每个服务器URL
        valid_urls = []
        for url in self.server_urls:
            if url.startswith(("http://", "https://")):
                valid_urls.append(url)
            else:
                logger.warning(f"无效的服务器URL: {url}")

        if not valid_urls:
            logger.error("没有有效的服务器地址")
            return False

        self.server_urls = valid_urls
        self.current_server = valid_urls[0]

        # 验证截图间隔
        if self.interval < 10 or self.interval > 3600:
            logger.warning(f"截图间隔{self.interval}秒不合理，调整为60秒")
            self.interval = 60

        # 验证图片质量
        if self.quality < 10 or self.quality > 100:
            logger.warning(f"图片质量{self.quality}不合理，调整为80")
            self.quality = 80

        # 验证图片格式
        if self.format not in ["webp", "jpg", "jpeg"]:
            logger.warning(f"图片格式{self.format}不合理，使用webp")
            self.format = "webp"

        return True

    def detect_best_server(self):
        """直接返回本地服务器地址，跳过检测"""
        local_server = "https://jk168.onrender.com"
        logger.info(f"🔧 直接使用本地服务器: {local_server}")

        # 简单测试一下连接是否成功
        try:
            response = requests.get(f"{local_server}/health", timeout=2, verify=False)
            if response.status_code == 200:
                logger.info(f"✅ 本地服务器连接成功")
            else:
                logger.warning(f"⚠️ 本地服务器返回状态码: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ 无法连接到本地服务器 {local_server}: {e}")
            logger.error("请确认服务器 (python server_main.py) 是否在运行")

        return local_server

    def register_with_server(self, silent_mode: bool = False):
        """向服务器注册（支持首次运行引导 & 图形界面）"""

        # ===== 1. 检测最佳服务器 =====
        self.current_server = self.detect_best_server()

        # ===== 2. 初始化API客户端 =====
        self.api_client = APIClient(
            self.current_server,
            retry_times=self.retry_times,
            retry_delay=self.retry_delay,
        )

        # ===== 3. 获取员工姓名 =====
        employee_name = None
        saved_name = self.config_manager.get("employee_name")
        if saved_name:
            employee_name = saved_name
            logger.info(f"从配置读取员工姓名: {employee_name}")

        # ... 姓名获取逻辑保持不变 ...

        # ===== 4. 如果已有 client_id，获取服务器配置 =====
        if self.client_id:
            logger.info(f"使用现有client_id: {self.client_id}")
            try:
                config = self.api_client.get(f"/api/client/{self.client_id}/config")
                if config:
                    self._update_config_from_server(config)
                    logger.info(f"✅ 从服务器获取配置成功")
            except Exception as e:
                logger.debug(f"获取服务器配置失败: {e}")

        # ===== 🚀 关键修复：构建完整的注册数据 =====
        system_info = self.system_info.get_system_info()

        # 构建符合服务器期望的数据结构
        register_data = {
            # 基础信息
            "client_id": self.client_id or None,
            "computer_name": system_info.get("computer_name"),
            "windows_user": system_info.get("windows_user"),
            "mac_address": system_info.get("mac_address"),
            "ip_address": system_info.get("ip_address"),
            "os_version": system_info.get("os_version"),
            "cpu_id": system_info.get("cpu_id"),
            "disk_serial": system_info.get("disk_serial"),
            "client_version": "3.0.1",
            # 配置信息（服务器会覆盖）
            "interval": self.interval,
            "quality": self.quality,
            "format": self.format,
            # 员工姓名（关键字段）
            "employee_name": employee_name,
            # 能力列表
            "capabilities": ["webp", "heartbeat", "batch", "encryption"],
        }

        # 移除None值，避免服务器端验证失败
        register_data = {k: v for k, v in register_data.items() if v is not None}

        logger.info(f"正在向服务器注册: {self.current_server}")
        logger.info(
            f"注册数据: {json.dumps(register_data, indent=2, ensure_ascii=False)}"
        )

        try:
            # 🚀 关键：直接传递字典，FastAPI会自动转换为Pydantic模型
            data = self.api_client.post("/api/client/register", json=register_data)

            self.client_id = data.get("client_id")
            self.employee_id = data.get("employee_id")

            if "config" in data:
                self._update_config_from_server(data["config"])

            logger.info(
                f"✅ 注册成功! 客户端ID: {self.client_id}, 员工ID: {self.employee_id}"
            )

            # 保存配置
            self.config_manager.update(
                client_id=self.client_id,
                employee_id=self.employee_id,
                interval=self.interval,
                quality=self.quality,
                format=self.format,
                employee_name=employee_name,
                version=self.CURRENT_VERSION,
            )

            return True

        except Exception as e:
            logger.error(f"注册失败: {e}")
            self.offline_mode = True
            return False

    def _update_config_from_server(self, config):
        """从服务器更新配置 - 服务器配置强制覆盖"""
        changed = False

        # 间隔配置 - 完全由服务器控制
        if config.get("interval") and config["interval"] != self.interval:
            self.interval = config["interval"]
            changed = True
            logger.info(f"【服务器强制】截图间隔更新为: {self.interval}秒")

        # 质量配置
        if config.get("quality") and config["quality"] != self.quality:
            self.quality = config["quality"]
            if self.screenshot_manager:
                self.screenshot_manager.quality = self.quality
            changed = True
            logger.info(f"【服务器强制】图片质量更新为: {self.quality}")

        # 格式配置
        if config.get("format") and config["format"] != self.format:
            self.format = config["format"]
            if self.screenshot_manager:
                self.screenshot_manager.format = self.format
            changed = True
            logger.info(f"【服务器强制】图片格式更新为: {self.format}")

        if changed:
            self.config_manager.update(
                interval=self.interval, quality=self.quality, format=self.format
            )

    @retry(max_retries=2)
    def send_heartbeat(self):
        """发送心跳 - 使用带时区的时间"""
        if not self.enable_heartbeat or self.offline_mode:
            return False
        if not self.api_client or not self.client_id:
            return False

        try:
            stats = self.system_info.get_system_stats()

            # 🚀 使用 aware datetime（带时区信息）
            # 推荐：使用带时区的 datetime
            current_time = datetime.now(timezone.utc)

            heartbeat_data = {
                "status": "online",
                "timestamp": current_time,  # 直接传 aware datetime
                "stats": stats,
                "client_stats": self.get_stats(),
                "paused": bool(self.paused),
                "ip_address": self.system_info.get_ip_address(),
            }

            self.api_client.post(
                f"/api/client/{self.client_id}/heartbeat", json=heartbeat_data
            )

            with self.stats_lock:
                self.stats["last_heartbeat"] = time.time()

            return True
        except Exception as e:
            logger.debug(f"心跳发送失败: {e}")
            return False

    # ===== 🚀 批量上传截图 =====
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

            logger.info(f"准备批量上传 {len(screenshots)} 个截图")

            # 创建ZIP文件
            import io
            import zipfile

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for screenshot in screenshots:
                    # 使用二进制模式读取文件并添加到ZIP
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
                        logger.warning(f"删除文件失败 {screenshot}: {e}")

                # 更新统计
                with self.stats_lock:
                    self.stats["screenshots_uploaded"] += len(screenshots)
                    self.stats["last_upload_time"] = time.time()

                logger.info(
                    f"✅ 批量上传成功: {len(screenshots)}个文件 (删除{deleted_count}个)"
                )
                return True
            else:
                logger.warning(f"批量上传失败: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"批量上传失败: {e}")
            return False

    def upload_cached_screenshots(self):
        """上传缓存的截图（网络恢复时调用）"""
        logger.info("开始上传缓存的截图...")
        try:
            # 查找所有本地截图
            pattern = f"screenshot_*.{self.format}"
            screenshots = list(Path(".").glob(pattern))

            if not screenshots:
                logger.info("没有缓存的截图")
                return

            logger.info(f"找到 {len(screenshots)} 个缓存的截图")

            for screenshot in screenshots:
                if not self.running:
                    break
                if self.offline_mode:
                    break
                self.upload_screenshot(str(screenshot))
                time.sleep(1)  # 避免上传过快
        except Exception as e:
            logger.error(f"上传缓存截图失败: {e}")

    @retry(max_retries=3)
    def upload_screenshot(self, image_path):
        """
        上传截图 - 完整修复版

        确保：
        - 字段类型正确（encrypted 为布尔值）
        - 时间格式正确（YYYY-MM-DD HH:MM:SS）
        - 正确处理响应
        - 完善的错误处理
        """
        if self.offline_mode:
            logger.debug("离线模式，保存截图到本地")
            return False

        if not self.api_client or not self.client_id:
            logger.error("API客户端未初始化或无客户端ID")
            return False

        # 检查文件是否存在
        if not os.path.exists(image_path):
            logger.error(f"文件不存在: {image_path}")
            return False

        file_size = os.path.getsize(image_path)
        logger.debug(f"准备上传文件: {image_path}, 大小: {file_size/1024:.1f}KB")

        try:
            # ========== 1. 准备数据 ==========
            # 生成时间戳（北京时间）
            from datetime import datetime, timezone, timedelta

            # 获取北京时间 (UTC+8)
            beijing_tz = timezone(timedelta(hours=8))
            now_beijing = datetime.now(beijing_tz)
            timestamp = now_beijing.strftime("%Y-%m-%d %H:%M:%S")

            # 获取系统信息
            computer_name = self.system_info.get_computer_name() or ""
            windows_user = self.system_info.get_windows_user() or ""

            # 🚀 确保 encrypted 是布尔值（不是字符串）
            encrypted_value = bool(self.encryption_enabled)

            logger.debug(
                f"上传参数: employee_id={self.employee_id}, client_id={self.client_id}"
            )
            logger.debug(f"时间戳(北京时间): {timestamp}")
            logger.debug(
                f"encrypted: {encrypted_value} (类型: {type(encrypted_value)})"
            )

            # ========== 2. 准备文件和数据 ==========
            with open(image_path, "rb") as f:
                # 文件部分
                files = {
                    "file": (
                        os.path.basename(image_path),
                        f,
                        "image/webp" if self.format == "webp" else "image/jpeg",
                    )
                }

                # 表单数据部分 - 所有字段都必须是字符串或字节
                # FastAPI 的 Form 参数期望字符串
                data = {
                    "employee_id": str(self.employee_id),
                    "client_id": str(self.client_id) if self.client_id else "",
                    "timestamp": timestamp,
                    "computer_name": computer_name,
                    "windows_user": windows_user,
                    # 🚀 重要：布尔值需要转换为字符串，因为 Form 参数期望字符串
                    "encrypted": str(encrypted_value).lower(),  # "true" 或 "false"
                    "format": self.format,
                }

                # 移除空值
                data = {k: v for k, v in data.items() if v}

                logger.debug(f"发送表单数据: {data}")

                # ========== 3. 发送请求 ==========
                response = self.api_client.session.post(
                    f"{self.current_server}/api/upload",
                    files=files,
                    data=data,  # 使用 data 参数发送表单数据
                    timeout=60,
                )

            # ========== 4. 处理响应 ==========
            if response.status_code == 200:
                result = response.json()

                # 更新统计
                with self.stats_lock:
                    self.stats["screenshots_uploaded"] += 1
                    self.stats["last_upload_time"] = time.time()

                logger.info(
                    f"✅ 截图上传成功: {os.path.basename(image_path)} "
                    f"(ID: {result.get('id')}, 大小: {result.get('size_str', f'{file_size/1024:.1f}KB')})"
                )

                # 删除本地文件
                try:
                    os.remove(image_path)
                    logger.debug(f"已删除本地文件: {image_path}")
                except Exception as e:
                    logger.warning(f"删除本地文件失败: {e}")

                return True

            elif response.status_code == 422:
                # 验证错误 - 打印详细信息
                try:
                    error_detail = response.json()
                    logger.error(
                        f"❌ 数据验证失败: {json.dumps(error_detail, indent=2, ensure_ascii=False)}"
                    )
                except:
                    logger.error(f"❌ 数据验证失败: {response.text}")

                with self.stats_lock:
                    self.stats["upload_failures"] += 1
                return False

            else:
                logger.warning(
                    f"上传失败: HTTP {response.status_code}\n"
                    f"响应: {response.text[:200]}"
                )
                with self.stats_lock:
                    self.stats["upload_failures"] += 1
                return False

        except requests.exceptions.Timeout:
            logger.error("上传超时")
            with self.stats_lock:
                self.stats["upload_failures"] += 1
            return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"连接错误: {e}")
            with self.stats_lock:
                self.stats["upload_failures"] += 1
            return False

        except Exception as e:
            logger.error(f"上传出错: {e}", exc_info=True)
            with self.stats_lock:
                self.stats["upload_failures"] += 1
            return False

    def get_stats(self):
        """获取统计信息"""
        with self.stats_lock:
            stats_copy = self.stats.copy()
            if stats_copy["start_time"]:
                stats_copy["uptime"] = time.time() - stats_copy["start_time"]
            return stats_copy

    def add_error(self, error):
        """记录错误"""
        with self.error_lock:
            self.stats["errors"].append(
                {"time": datetime.now().isoformat(), "error": str(error)}
            )
            if len(self.stats["errors"]) > 10:
                self.stats["errors"] = self.stats["errors"][-10:]

    def config_watcher(self):
        """配置文件监控线程"""
        while self.running:
            try:
                if self.config_manager.reload_if_changed():
                    old_interval = self.interval
                    self._load_config()
                    if old_interval != self.interval:
                        logger.info(f"截图间隔已更新为: {self.interval}秒")
            except Exception as e:
                logger.error(f"配置监控出错: {e}")

            time.sleep(5)

    def heartbeat_sender(self):
        """心跳发送线程 - 工业级实现"""

        heartbeat_failures = 0

        while self.running:

            try:
                if not self.offline_mode:
                    success = self.send_heartbeat()

                    if success:
                        # 心跳成功，重置失败计数
                        if heartbeat_failures > 0:
                            logger.info("心跳恢复")
                        heartbeat_failures = 0
                    else:
                        heartbeat_failures += 1

                        # 分级日志
                        if heartbeat_failures == 1:
                            logger.warning("⚠️ 心跳发送失败 (第1次)")
                        elif heartbeat_failures == 2:
                            logger.warning("⚠️ 心跳发送失败 (第2次)")
                        elif heartbeat_failures >= 3:
                            logger.warning("⚠️ 连续3次心跳失败，触发网络检测")

                            # 通知网络线程立即检测
                            self.force_network_check = True

                            # 重置失败计数，避免无限触发
                            heartbeat_failures = 0
                else:
                    # 离线模式，重置失败计数
                    heartbeat_failures = 0

            except Exception as e:
                logger.debug(f"心跳异常: {e}")
                heartbeat_failures += 1

            # 可中断sleep（60秒间隔）
            for _ in range(60):
                if not self.running:
                    return
                time.sleep(1)

    def batch_uploader(self):
        """批量上传线程"""
        while self.running:
            time.sleep(1800)
            if self.running and not self.offline_mode:
                try:
                    self.upload_screenshots_batch()
                except Exception as e:
                    logger.error(f"批量上传失败: {e}")

    def network_monitor(self):
        """工业级网络监控线程"""

        consecutive_failures = 0
        current_server_index = 0

        # 网络退避参数
        base_interval = 30
        max_interval = 300
        check_interval = base_interval

        session = requests.Session()

        # 上次检查时间
        last_check_time = time.time()

        while self.running:

            # ===== 响应心跳线程的强制检查请求 =====
            current_time = time.time()
            force_check = False

            if self.force_network_check:
                logger.info("收到强制网络检测请求")
                self.force_network_check = False
                force_check = True
                check_interval = base_interval  # 重置间隔

            # ===== 判断是否需要进行健康检测 =====
            time_since_last_check = current_time - last_check_time

            if force_check or time_since_last_check >= check_interval:

                last_check_time = current_time

                try:
                    # ========== 健康检测 ==========
                    response = session.get(
                        f"{self.current_server}/health", timeout=5, verify=False
                    )

                    if response.status_code == 200:
                        # 网络恢复
                        if self.offline_mode:
                            logger.info("🌐 网络恢复，重新连接服务器")

                            self.offline_mode = False
                            consecutive_failures = 0
                            check_interval = base_interval

                            # 重新注册
                            try:
                                self.register_with_server()
                            except Exception as e:
                                logger.error(f"重新注册失败: {e}")

                            # 异步补传截图
                            if self.screenshot_manager:
                                threading.Thread(
                                    target=self.upload_cached_screenshots, daemon=True
                                ).start()
                        else:
                            consecutive_failures = 0
                            check_interval = base_interval
                    else:
                        consecutive_failures += 1

                except requests.RequestException as e:
                    logger.debug(f"健康检测失败: {e}")
                    consecutive_failures += 1

                # ========== 服务器故障处理 ==========
                if consecutive_failures >= 3:
                    logger.warning("服务器连接失败，尝试切换服务器")

                    current_server_index = (current_server_index + 1) % len(
                        self.server_urls
                    )

                    new_server = self.server_urls[current_server_index]

                    logger.warning(f"切换服务器 → {new_server}")

                    self.current_server = new_server

                    # 更新API客户端
                    self.api_client = APIClient(
                        self.current_server,
                        retry_times=self.retry_times,
                        retry_delay=self.retry_delay,
                    )

                    consecutive_failures = 0

                    # 所有服务器都尝试后进入离线模式
                    if current_server_index == 0:
                        if not self.offline_mode:
                            logger.warning("⚠️ 所有服务器不可用，进入离线模式")

                            self.offline_mode = True

                            if self.config_manager:
                                self.config_manager.save()

                # ========== 指数退避 ==========
                if consecutive_failures > 0:
                    check_interval = min(check_interval * 2, max_interval)

                # ========== 随机抖动 ==========
                jitter = random.uniform(0, 5)
                adjusted_interval = check_interval + jitter

                logger.debug(f"下次检测 {adjusted_interval:.1f}s 后")

            # 可中断的短sleep（1秒，以便快速响应强制检查）
            for _ in range(1):
                if not self.running:
                    return
                time.sleep(1)

    def work_loop(self):
        """主工作循环 - 固定时间点截图 + 防抖"""
        logger.info(f"开始监控，员工ID: {self.employee_id}")
        logger.info(f"截图间隔: {self.interval}秒")
        logger.info(f"图片格式: {self.format}")

        import math

        last_sync = 0
        consecutive_failures = 0
        last_screenshot_path = None
        last_screenshot_time = 0  # 记录上次实际截图时间，用于防抖

        # 计算下一个截图时间点（对齐到整分钟/整间隔）
        now = time.time()
        next_screenshot = math.ceil(now / self.interval) * self.interval
        logger.info(
            f"首次截图时间点: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_screenshot))}"
        )

        while self.running:
            try:
                if self.paused:
                    time.sleep(5)
                    continue

                now = time.time()

                # ===== 立即截图请求处理 =====
                if self.take_screenshot_now:
                    self.take_screenshot_now = False
                    logger.info("执行立即截图")

                    # 立即截图
                    image_path = self._take_and_process_screenshot(
                        last_screenshot_path, consecutive_failures
                    )
                    if image_path:
                        last_screenshot_path = image_path
                        last_screenshot_time = now

                    # 立即截图后，重新计算下一个截图时间点，避免打乱节奏
                    next_screenshot = math.ceil(now / self.interval) * self.interval
                    logger.debug(
                        f"立即截图后，下次截图时间调整为: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_screenshot))}"
                    )

                # ===== 定时截图检查 =====
                elif now >= next_screenshot:
                    # 防抖检查：避免在极短时间内重复截图（比如1秒内）
                    if now - last_screenshot_time < 2:  # 2秒内不重复截图
                        logger.debug(
                            f"截图太频繁（上次截图在{now - last_screenshot_time:.1f}秒前），跳过本次"
                        )
                        # 仍然需要更新时间点，避免卡死
                        next_screenshot = math.ceil(now / self.interval) * self.interval
                        time.sleep(1)
                        continue

                    logger.debug(
                        f"到达截图时间点: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}"
                    )

                    # 执行截图和上传
                    image_path = self._take_and_process_screenshot(
                        last_screenshot_path, consecutive_failures
                    )

                    if image_path:
                        last_screenshot_path = image_path
                        last_screenshot_time = now

                    # 计算下一个截图时间点（保持固定间隔）
                    next_screenshot = math.ceil(now / self.interval) * self.interval
                    logger.debug(
                        f"下次截图时间点: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_screenshot))}"
                    )

                # ===== 同步配置（每10分钟） =====
                if now - last_sync > 600 and not self.offline_mode:
                    try:
                        config = self.api_client.get(
                            f"/api/client/{self.client_id}/config"
                        )
                        if config:
                            self._update_config_from_server(config)
                            # 如果配置的间隔变了，重新计算下一个截图时间点
                            new_interval = config.get("interval")
                            if new_interval and new_interval != self.interval:
                                logger.info(
                                    f"截图间隔已从 {self.interval}秒 变为 {new_interval}秒，重新计算时间点"
                                )
                                self.interval = new_interval
                                next_screenshot = (
                                    math.ceil(now / self.interval) * self.interval
                                )
                    except Exception as e:
                        logger.debug(f"同步配置失败: {e}")
                    last_sync = now

                # 动态计算等待时间（避免CPU占用）
                # 如果距离下次截图时间还早，可以适当延长休眠时间
                time_to_next = next_screenshot - time.time()
                if time_to_next > 5:
                    # 如果离下次截图还有5秒以上，先睡2秒再继续检查
                    sleep_time = min(2, time_to_next - 1)
                    time.sleep(sleep_time)
                else:
                    # 快到了，每秒检查一次
                    time.sleep(1)

            except Exception as e:
                logger.error(f"工作循环出错: {e}")
                self.add_error(e)
                time.sleep(60)

    def _take_and_process_screenshot(self, last_screenshot_path, consecutive_failures):
        """
        抽取截图处理逻辑为独立方法，避免代码重复
        返回新截图的路径，如果没有截图或处理失败返回None
        """
        try:
            # 截图
            image_path = self.screenshot_manager.take_screenshot()
            if not image_path:
                logger.error("截图失败")
                return None

            with self.stats_lock:
                self.stats["screenshots_taken"] += 1

            # 检查是否与上一张相似
            if last_screenshot_path and self.screenshot_manager.are_similar(
                last_screenshot_path, image_path
            ):
                logger.debug("屏幕内容无变化，跳过上传")
                os.remove(image_path)
                consecutive_failures = 0  # 重置失败计数
                return None
            else:
                # 上传截图
                if self.upload_screenshot(image_path):
                    consecutive_failures = 0
                    # 删除上一张截图（如果存在）
                    if last_screenshot_path and os.path.exists(last_screenshot_path):
                        try:
                            os.remove(last_screenshot_path)
                            logger.debug(f"已删除上一张截图: {last_screenshot_path}")
                        except Exception as e:
                            logger.debug(f"删除上一张截图失败: {e}")
                    self.screenshot_manager.last_screenshot_path = image_path
                    return image_path
                else:
                    consecutive_failures += 1
                    logger.warning(
                        f"上传失败，保留本地文件 (连续失败: {consecutive_failures})"
                    )

                    if consecutive_failures > 5:
                        # 连续失败次数过多，调整截图间隔
                        new_interval = min(self.interval * 2, 3600)
                        if new_interval != self.interval:
                            logger.warning(
                                f"连续失败次数过多，调整截图间隔为: {new_interval}秒"
                            )
                            self.interval = new_interval
                            self.config_manager.set("interval", self.interval)
                    return None

        except Exception as e:
            logger.error(f"截图处理过程出错: {e}")
            return None

    def start(self, silent_mode=False):
        """启动监控"""
        logger.info("=" * 50)
        logger.info("员工监控系统客户端 v3.0")
        logger.info("=" * 50)

        # 验证配置
        if not self.validate_config():
            logger.error("配置验证失败，程序退出")
            return

        # 注册到服务器（传递 silent_mode 参数）
        if not self.register_with_server(silent_mode=silent_mode):
            logger.warning("注册失败，将以离线模式运行")
            self.offline_mode = True

        self.running = True
        self.stats["start_time"] = time.time()

        # 启动工作线程
        threads = [
            threading.Thread(target=self.work_loop, name="WorkLoop", daemon=True),
            threading.Thread(
                target=self.config_watcher, name="ConfigWatcher", daemon=True
            ),
            threading.Thread(
                target=self.heartbeat_sender, name="Heartbeat", daemon=True
            ),
            threading.Thread(
                target=self.batch_uploader, name="BatchUploader", daemon=True
            ),
            threading.Thread(
                target=self.network_monitor, name="NetworkMonitor", daemon=True
            ),
        ]

        for thread in threads:
            thread.start()
            logger.debug(f"线程已启动: {thread.name}")

        logger.info("监控程序启动成功")

        # 运行托盘图标 - 放在独立线程中
        if self.tray:
            # 在新线程中运行托盘图标
            tray_thread = threading.Thread(
                target=self.tray.run, name="TrayIcon", daemon=True
            )
            tray_thread.start()
            logger.info("✅ 托盘图标线程已启动")

            # 主线程保持运行，等待退出信号
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()
        else:
            # 没有托盘图标时的原有逻辑
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        """停止监控"""
        logger.info("正在停止监控程序...")
        self.running = False

        # 清理旧截图
        self.screenshot_manager.cleanup_old_screenshots()

        # 发送最后一次心跳
        if not self.offline_mode:
            self.send_heartbeat()

        # 统计信息
        uptime = time.time() - self.stats["start_time"]
        logger.info("=" * 50)
        logger.info("监控程序停止")
        logger.info(f"运行时间: {uptime/3600:.2f}小时")
        logger.info(f"截图数量: {self.stats['screenshots_taken']}")
        logger.info(f"上传成功: {self.stats['screenshots_uploaded']}")
        logger.info(f"上传失败: {self.stats['upload_failures']}")
        logger.info("=" * 50)

    def test_mode(self):
        """测试模式"""
        print("\n" + "=" * 50)
        print("测试模式 - 立即截图并上传")
        print("=" * 50)

        if not self.register_with_server():
            logger.error("注册失败")
            return

        print(f"客户端ID: {self.client_id}")
        print(f"员工ID: {self.employee_id}")
        print(f"服务器: {self.current_server}")
        print(f"图片格式: {self.format}")
        print("-" * 50)

        # 截图
        print("正在截图...")
        image_path = self.screenshot_manager.take_screenshot()

        if image_path:
            print(f"✅ 截图成功: {os.path.basename(image_path)}")
            print(f"文件大小: {os.path.getsize(image_path)/1024:.1f}KB")

            # 上传
            print("正在上传...")
            if self.upload_screenshot(image_path):
                print("✅ 上传成功")
            else:
                print("❌ 上传失败")
        else:
            print("❌ 截图失败")

        print("=" * 50)


class APIClient:
    """API客户端 - 修复版：增强错误处理和日志"""

    def __init__(self, base_url, timeout=30, retry_times=3, retry_delay=1):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.last_error = None
        self.error_count = 0

        # 设置默认头
        self.session.headers.update(
            {
                "User-Agent": f"MonitorClient/{platform.platform()}",
                "Accept": "application/json",
                "Content-Type": "application/json",  # 默认JSON
            }
        )

        # 配置重试
        adapter = requests.adapters.HTTPAdapter(
            max_retries=retry_times, pool_connections=10, pool_maxsize=10
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @retry()
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
            logger.error(f"GET请求失败 {url}: {e}")
            raise

    @retry()
    def post(self, endpoint, **kwargs):
        """POST请求 - 增强版"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", False)

        # 🚀 如果传了json参数，设置正确的Content-Type
        if "json" in kwargs:
            headers = kwargs.get("headers", {})
            headers["Content-Type"] = "application/json"
            kwargs["headers"] = headers
            logger.debug(f"POST JSON: {url} - {json.dumps(kwargs['json'], indent=2)}")
        # 如果有files参数，移除Content-Type（让requests自动设置）
        elif "files" in kwargs:
            if "headers" in kwargs:
                kwargs["headers"].pop("Content-Type", None)

        try:
            response = self.session.post(url, **kwargs)
            response.raise_for_status()
            self.error_count = 0
            self.last_error = None
            return response.json() if response.content else None
        except requests.exceptions.HTTPError as e:
            self.error_count += 1
            self.last_error = str(e)
            # 尝试读取错误响应体
            try:
                error_detail = response.json().get("detail", str(e))
            except:
                error_detail = response.text or str(e)
            logger.error(f"POST请求失败 {url}: {error_detail}")
            raise Exception(error_detail)
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            logger.error(f"POST请求失败 {url}: {e}")
            raise


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

        self.last_screenshot_path = None
        self.screenshot_history = []
        self.stats = {"taken": 0, "uploaded": 0, "skipped": 0, "failed": 0}

        if self.format not in ["webp", "jpg", "jpeg"]:
            logger.warning(f"不支持的图片格式 {self.format}，使用 webp")
            self.format = "webp"

    def take_screenshot(self):
        """截取屏幕"""
        try:
            screenshot = ImageGrab.grab(all_screens=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.{self.format}"
            filepath = os.path.join(os.getcwd(), filename)

            if self.format == "webp":
                screenshot.save(
                    filepath, "WEBP", quality=self.quality, optimize=True, method=6
                )
            else:
                screenshot.save(filepath, "JPEG", quality=self.quality, optimize=True)

            file_size = os.path.getsize(filepath)

            self.screenshot_history.append(filepath)
            if len(self.screenshot_history) > self.max_history:
                old_file = self.screenshot_history.pop(0)
                if os.path.exists(old_file) and old_file != self.last_screenshot_path:
                    try:
                        os.remove(old_file)
                    except Exception:
                        pass

            self.stats["taken"] += 1
            logger.info(
                f"✅ 截图成功: {filename} ({file_size/1024:.1f}KB, {self.format})"
            )
            return filepath

        except Exception as e:
            logger.error(f"❌ 截图失败: {e}")
            return None

    def encrypt_screenshot(self, image_path):
        """加密截图文件"""
        try:
            from cryptography.fernet import Fernet

            cipher = Fernet(self.encryption_key.encode())

            with open(image_path, "rb") as f:
                image_data = f.read()

            encrypted_data = cipher.encrypt(image_data)
            encrypted_path = image_path + ".encrypted"

            with open(encrypted_path, "wb") as f:
                f.write(encrypted_data)

            os.remove(image_path)
            logger.debug(f"🔐 截图已加密: {os.path.basename(encrypted_path)}")
            return encrypted_path

        except Exception as e:
            logger.error(f"❌ 加密失败: {e}")
            return image_path

    def are_similar(self, img1_path, img2_path):
        """判断两张图片是否相似"""
        if (
            not img1_path
            or not img2_path
            or not os.path.exists(img1_path)
            or not os.path.exists(img2_path)
        ):
            return False

        try:
            # 快速比较：文件大小
            size1 = os.path.getsize(img1_path)
            size2 = os.path.getsize(img2_path)
            if abs(size1 - size2) / max(size1, size2) > 0.3:
                return False

            # 计算文件哈希
            hash1 = hashlib.md5(open(img1_path, "rb").read()).hexdigest()
            hash2 = hashlib.md5(open(img2_path, "rb").read()).hexdigest()

            if hash1 == hash2:
                return True

            # 如果哈希不同，比较图片内容
            img1 = Image.open(img1_path)
            img2 = Image.open(img2_path)

            img1 = img1.resize((200, 200)).convert("L")
            img2 = img2.resize((200, 200)).convert("L")

            h1 = img1.histogram()
            h2 = img2.histogram()

            import math

            mean1 = sum(h1) / len(h1)
            mean2 = sum(h2) / len(h2)

            numerator = sum((a - mean1) * (b - mean2) for a, b in zip(h1, h2))
            denominator = math.sqrt(
                sum((a - mean1) ** 2 for a in h1) * sum((b - mean2) ** 2 for b in h2)
            )

            if denominator == 0:
                return False

            correlation = numerator / denominator
            similarity = (correlation + 1) / 2

            return similarity >= self.similarity_threshold

        except Exception as e:
            logger.debug(f"图片比较失败: {e}")
            return False

    def cleanup_old_screenshots(self, max_age_hours=24):
        """清理旧截图"""
        try:
            now = time.time()
            pattern = f"screenshot_*.{self.format}"
            count = 0
            size_freed = 0

            for file in Path(".").glob(pattern):
                file_age = now - file.stat().st_mtime
                if file_age > max_age_hours * 3600:
                    size_freed += file.stat().st_size
                    file.unlink()
                    count += 1

            if count > 0:
                logger.info(
                    f"清理了 {count} 个旧截图，释放 {size_freed/1024/1024:.2f}MB"
                )

        except Exception as e:
            logger.error(f"清理旧截图失败: {e}")

    def get_stats(self):
        """获取截图统计"""
        return self.stats.copy()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="员工监控系统客户端 - 完整增强版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-c", "--config", default="config.json", help="配置文件路径 (默认: config.json)"
    )
    parser.add_argument("--test", action="store_true", help="测试模式：立即截图并上传")
    parser.add_argument("--register", action="store_true", help="仅注册，不启动监控")
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
    parser.add_argument("--version", action="version", version="员工监控系统客户端 3.0")
    # ===== 可选：添加静默模式参数 =====
    parser.add_argument(
        "--silent", action="store_true", help="静默模式，不显示交互界面"
    )
    # ================================

    args = parser.parse_args()

    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # 创建客户端实例
    client = MonitorClient(args.config)

    # 命令行参数覆盖配置
    if args.server:
        client.server_urls = args.server
        client.config_manager.set("server_urls", args.server)
        logger.info(f"使用命令行指定的服务器: {args.server}")

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
            # ===== 修改：加上 silent_mode 参数 =====
            client.register_with_server(silent_mode=args.silent)
            # ======================================
        else:
            # ===== 修改：start 方法内部会调用 register_with_server =====
            # 需要在 start 方法中修改调用方式
            client.start(silent_mode=args.silent)  # ← 如果 start 也需要
            # =======================================================
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
