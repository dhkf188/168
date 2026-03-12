"""
客户端工具模块
"""

import os
import sys
import json
import time
import socket
import platform
import logging
import threading
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
import requests

# 可选导入
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import winreg

    WINREG_AVAILABLE = True
except ImportError:
    WINREG_AVAILABLE = False

try:
    from plyer import notification

    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

try:
    from PIL import Image, ImageDraw
    import pystray

    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False


def setup_logging(log_level=logging.INFO, log_file="monitor.log"):
    """配置日志系统"""
    log_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 确保日志目录存在
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(log_formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.WARNING)

    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return logging.getLogger(__name__)


def retry(max_retries=None, delay=None, backoff=2, exceptions=(Exception,)):
    """
    重试装饰器
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            instance = args[0] if args else None
            max_retries_val = max_retries
            delay_val = delay

            if hasattr(instance, "retry_times") and max_retries is None:
                max_retries_val = instance.retry_times
            if hasattr(instance, "retry_delay") and delay is None:
                delay_val = instance.retry_delay

            max_retries_val = max_retries_val or 3
            delay_val = delay_val or 1

            _delay = delay_val
            for i in range(max_retries_val):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if i == max_retries_val - 1:
                        raise
                    time.sleep(_delay)
                    _delay *= backoff
            return None

        return wrapper

    return decorator


class SystemInfoCollector:
    """系统信息收集器"""

    @staticmethod
    def get_mac_address():
        """获取MAC地址"""
        try:
            mac = uuid.getnode()
            if (mac >> 40) % 2 == 0:
                return ":".join(("%012X" % mac)[i : i + 2] for i in range(0, 12, 2))

            # 备选方案
            computer_name = socket.gethostname()
            user_name = os.environ.get("USERNAME", "") or os.environ.get("USER", "")
            unique_str = f"{computer_name}-{user_name}"
            hash_obj = hashlib.md5(unique_str.encode())
            return ":".join(hash_obj.hexdigest()[i : i + 2] for i in range(0, 12, 2))

        except Exception:
            return "00:00:00:00:00:00"

    @staticmethod
    def get_computer_name():
        """获取计算机名"""
        try:
            return socket.gethostname()
        except:
            return "UNKNOWN"

    @staticmethod
    def get_ip_address():
        """获取IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            try:
                return socket.gethostbyname(socket.gethostname())
            except:
                return "127.0.0.1"

    @staticmethod
    def get_windows_user():
        """获取Windows用户名"""
        try:
            return os.environ.get("USERNAME") or os.environ.get("USER")
        except:
            return None

    @staticmethod
    def get_disk_serial():
        """获取磁盘序列号"""
        if sys.platform != "win32":
            return None

        try:
            import wmi

            c = wmi.WMI()
            for disk in c.Win32_DiskDrive():
                return disk.SerialNumber.strip()
        except:
            pass
        return None

    @staticmethod
    def get_cpu_id():
        """获取CPU ID"""
        if sys.platform == "win32":
            try:
                import wmi

                c = wmi.WMI()
                for cpu in c.Win32_Processor():
                    return cpu.ProcessorId.strip()
            except:
                pass
        return None

    @staticmethod
    def get_system_info():
        """获取完整的系统信息"""
        info = {
            "computer_name": SystemInfoCollector.get_computer_name(),
            "mac_address": SystemInfoCollector.get_mac_address(),
            "ip_address": SystemInfoCollector.get_ip_address(),
            "windows_user": SystemInfoCollector.get_windows_user(),
            "disk_serial": SystemInfoCollector.get_disk_serial(),
            "cpu_id": SystemInfoCollector.get_cpu_id(),
            "os_version": platform.platform(),
            "os_release": platform.release(),
            "os_arch": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "system": platform.system(),
        }

        if PSUTIL_AVAILABLE:
            try:
                info["cpu_count"] = psutil.cpu_count()
                info["memory_total"] = psutil.virtual_memory().total
                info["disk_total"] = psutil.disk_usage("/").total
            except:
                pass

        return info

    @staticmethod
    def get_system_stats():
        """获取系统实时状态"""
        if not PSUTIL_AVAILABLE:
            return {}

        try:
            cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            stats = {
                "cpu_percent": cpu_percent,
                "cpu_percent_avg": sum(cpu_percent) / len(cpu_percent),
                "memory_percent": memory.percent,
                "memory_used": memory.used,
                "disk_usage": disk.percent,
                "timestamp": datetime.now().isoformat(),
            }

            return stats
        except Exception:
            return {}


class ConfigManager:
    """配置管理器"""

    # 从 client_config.py 导入配置
    from client_config import Config as ClientConfig

    CONFIG_VERSION = "3.0.1"

    DEFAULT_CONFIG = {
        # ===== 添加版本字段 =====
        "version": CONFIG_VERSION,
        # =====================
        "server_urls": ClientConfig.DEFAULT_SERVERS,
        "interval": ClientConfig.SCREENSHOT_INTERVAL,
        "quality": ClientConfig.SCREENSHOT_QUALITY,
        "format": ClientConfig.SCREENSHOT_FORMAT,
        "client_id": "",
        "employee_id": "",
        "employee_name": "",
        "auto_start": True,
        "hide_window": True,
        "enable_heartbeat": True,
        "enable_batch_upload": True,
        "max_history": ClientConfig.MAX_HISTORY,
        "similarity_threshold": ClientConfig.SIMILARITY_THRESHOLD,
        "retry_times": ClientConfig.RETRY_TIMES,
        "retry_delay": ClientConfig.RETRY_DELAY,
        "encryption_enabled": False,
        "last_update": None,
    }

    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.config = self.DEFAULT_CONFIG.copy()
        self.lock = threading.RLock()
        self.last_mtime = 0
        self.load()

    def load(self):
        """加载配置文件"""
        with self.lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        loaded_config = json.load(f)

                    # 合并配置
                    self.config.update(loaded_config)
                    self.last_mtime = os.path.getmtime(self.config_file)
                    return True
                except Exception as e:
                    print(f"加载配置文件失败: {e}")

            # 创建默认配置
            self.save()
            return False

    def save(self):
        """保存配置（自动更新版本号）"""
        with self.lock:
            try:
                # ===== 确保版本号是最新的 =====
                self.config["version"] = self.CONFIG_VERSION  # ← 添加这一行
                self.config["last_update"] = datetime.now().isoformat()
                # ============================

                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                self.last_mtime = os.path.getmtime(self.config_file)
                return True
            except Exception as e:
                print(f"保存配置失败: {e}")
                return False

    def get(self, key, default=None):
        """获取配置项"""
        with self.lock:
            return self.config.get(key, default)

    def set(self, key, value):
        """设置配置项"""
        with self.lock:
            self.config[key] = value
            self.save()

    def update(self, **kwargs):
        """批量更新配置"""
        with self.lock:
            self.config.update(kwargs)
            self.save()

    def has_changed(self):
        """检查配置文件是否已更改"""
        if os.path.exists(self.config_file):
            mtime = os.path.getmtime(self.config_file)
            return mtime > self.last_mtime
        return False

    def reload_if_changed(self):
        """如果文件已更改则重新加载"""
        if self.has_changed():
            return self.load()
        return False


class TrayIcon:
    """系统托盘图标管理"""

    def __init__(self, client):
        self.client = client
        self.icon = None
        self.create_icon()

    def create_icon(self):
        """创建托盘图标"""
        if not PYSTRAY_AVAILABLE:
            return

        # 创建图标图像
        image = self._create_icon_image()

        # 创建菜单
        menu = (
            pystray.MenuItem("📊 显示状态", self.show_status),
            pystray.MenuItem(
                "⏸️ 暂停监控",
                self.pause_monitor,
                enabled=lambda item: not self.client.paused,
            ),
            pystray.MenuItem(
                "▶️ 恢复监控",
                self.resume_monitor,
                enabled=lambda item: self.client.paused,
            ),
            pystray.MenuItem("🔄 立即截图", self.take_screenshot_now),
            pystray.MenuItem(
                "⚡ 开机自启",
                self.toggle_autostart,
                checked=lambda item: self.is_autostart_enabled(),
            ),
            pystray.MenuItem("📝 查看日志", self.open_log),
            pystray.MenuItem("❌ 退出", self.exit_app),
        )

        self.icon = pystray.Icon("employee_monitor", image, "员工监控系统", menu)

    def _create_icon_image(self):
        """创建图标图像"""
        image = Image.new("RGB", (64, 64), color=(102, 126, 234))
        draw = ImageDraw.Draw(image)

        # 绘制相机图标
        draw.rectangle([16, 20, 48, 44], outline=(255, 255, 255), width=2)
        draw.ellipse([28, 28, 36, 36], fill=(255, 255, 255))
        draw.line([40, 28, 44, 24], fill=(255, 255, 255), width=2)

        return image

    def show_status(self):
        """显示状态"""
        stats = self.client.get_stats()
        uptime = stats.get("uptime", 0)
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)

        message = (
            f"员工ID: {self.client.employee_id}\n"
            f"服务器: {self.client.current_server}\n"
            f"运行时间: {hours}小时{minutes}分钟\n"
            f"截图数量: {stats['screenshots_taken']}\n"
            f"上传成功: {stats['screenshots_uploaded']}\n"
            f"截图间隔: {self.client.interval}秒"
        )

        if PLYER_AVAILABLE:
            notification.notify(title="员工监控系统", message=message, timeout=5)
        else:
            print(message)

    def pause_monitor(self):
        """暂停监控"""
        self.client.paused = True
        if self.icon:
            self.icon.title = "员工监控系统 - 已暂停"

    def resume_monitor(self):
        """恢复监控"""
        self.client.paused = False
        if self.icon:
            self.icon.title = "员工监控系统"

    def take_screenshot_now(self):
        """立即截图"""
        self.client.take_screenshot_now = True

    def toggle_autostart(self):
        """切换开机自启"""
        if self.is_autostart_enabled():
            self.disable_autostart()
        else:
            self.enable_autostart()

    def is_autostart_enabled(self):
        """检查是否已启用开机自启"""
        if not WINREG_AVAILABLE or sys.platform != "win32":
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            )
            winreg.QueryValueEx(key, "EmployeeMonitor")
            winreg.CloseKey(key)
            return True
        except:
            return False

    def enable_autostart(self):
        """启用开机自启"""
        if not WINREG_AVAILABLE or sys.platform != "win32":
            return

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )

            if getattr(sys, "frozen", False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{__file__}"'

            winreg.SetValueEx(key, "EmployeeMonitor", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)

        except Exception as e:
            print(f"设置开机自启失败: {e}")

    def disable_autostart(self):
        """禁用开机自启"""
        if not WINREG_AVAILABLE or sys.platform != "win32":
            return

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            winreg.DeleteValue(key, "EmployeeMonitor")
            winreg.CloseKey(key)
        except:
            pass

    def open_log(self):
        """打开日志文件"""
        log_file = "monitor.log"
        if os.path.exists(log_file):
            if sys.platform == "win32":
                os.startfile(log_file)
            elif sys.platform == "darwin":
                import subprocess

                subprocess.run(["open", log_file])

    def exit_app(self):
        """退出应用"""
        if self.icon:
            self.icon.stop()
        self.client.running = False
        self.client.stop()
        os._exit(0)

    def run(self):
        """运行托盘图标"""
        if self.icon:
            self.icon.run()


class AutoConfig:
    """自动配置管理器"""

    @classmethod
    def detect_server(cls, servers, timeout=3):
        """自动检测可用的服务器"""
        for server in servers:
            try:
                response = requests.get(
                    f"{server}/health", timeout=timeout, verify=False
                )
                if response.status_code == 200:
                    return server
            except:
                continue
        return servers[0] if servers else None
