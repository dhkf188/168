#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
员工监控系统 - 核心模块
包含所有核心类和工具函数
"""

import os
import sys
import time
import json
import socket
import uuid
import logging
import platform
import hashlib
import threading
import io
import tempfile
import shutil
import queue
import random
from collections import deque
from datetime import datetime
from pathlib import Path
from functools import wraps
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum

import requests
from PIL import Image, ImageGrab

# 尝试导入可选依赖
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import imagehash

    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

try:
    import mss

    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False


# ========== 工具函数 ==========
def setup_logging(log_level=logging.INFO, log_file="monitor.log"):
    """配置日志系统"""
    log_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(log_formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.WARNING)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return logging.getLogger(__name__)


def retry(max_retries=None, delay=None, backoff=2, exceptions=(Exception,)):
    """重试装饰器"""

    def decorator(func):
        @wraps(func)
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


def smart_retry(
    max_retries=3,
    base_delay=2,
    max_delay=120,
    jitter=5,
    exceptions=(Exception,),
    no_retry_status_codes=(400, 401, 403, 404, 405),
):
    """智能指数退避重试装饰器"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            logger = logging.getLogger(__name__)

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.HTTPError as e:
                    if hasattr(e, "response") and e.response:
                        if e.response.status_code in no_retry_status_codes:
                            logger.warning(f"HTTP {e.response.status_code} 不重试")
                            raise
                    last_exception = e
                except exceptions as e:
                    last_exception = e
                except Exception as e:
                    raise e

                if attempt == max_retries - 1:
                    logger.error(f"函数 {func.__name__} 在 {max_retries} 次尝试后失败")
                    raise last_exception

                delay = min(base_delay * (2**attempt), max_delay)
                if jitter > 0:
                    delay += random.uniform(0, jitter)

                logger.warning(
                    f"重试 ({attempt + 1}/{max_retries})，{delay:.1f}秒后重试"
                )
                time.sleep(delay)
            return None

        return wrapper

    return decorator


# ========== 原子文件操作 ==========
class AtomicFileOperation:
    """原子文件操作类"""

    @staticmethod
    def atomic_write(filepath: str, data: bytes, mode: str = "wb") -> bool:
        """原子写入"""
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(
                mode=mode,
                dir=filepath.parent,
                prefix=".tmp_",
                suffix=filepath.suffix,
                delete=False,
            ) as tmp_file:
                tmp_file.write(data)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
                tmp_path = tmp_file.name

            shutil.move(tmp_path, filepath)
            return True
        except Exception as e:
            logging.getLogger(__name__).error(f"原子写入失败 {filepath}: {e}")
            try:
                if "tmp_path" in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except:
                pass
            return False

    @staticmethod
    def atomic_read(filepath: str) -> Optional[bytes]:
        """原子读取"""
        try:
            filepath = Path(filepath)
            if not filepath.exists() or filepath.name.startswith(".tmp_"):
                return None
            with open(filepath, "rb") as f:
                return f.read()
        except Exception as e:
            logging.getLogger(__name__).error(f"原子读取失败 {filepath}: {e}")
            return None

    @staticmethod
    def atomic_delete(filepath: str) -> bool:
        """原子删除"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                return True
            tmp_path = filepath.parent / f".tmp_del_{filepath.name}"
            shutil.move(str(filepath), str(tmp_path))
            os.unlink(tmp_path)
            return True
        except Exception as e:
            logging.getLogger(__name__).error(f"原子删除失败 {filepath}: {e}")
            return False


# ========== 缓冲区池 ==========
class BufferPool:
    """缓冲区池单例"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, max_size: int = 10, buffer_size: int = 10 * 1024 * 1024):
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

        for _ in range(max_size // 2):
            self._create_buffer()

    def _create_buffer(self) -> io.BytesIO:
        buffer = io.BytesIO()
        buffer.seek(0)
        buffer.truncate(0)
        with self.stats_lock:
            self.stats["created"] += 1
        return buffer

    def acquire(self) -> io.BytesIO:
        try:
            buffer = self.pool.get_nowait()
            with self.stats_lock:
                self.stats["acquired"] += 1
        except queue.Empty:
            buffer = self._create_buffer()
            with self.stats_lock:
                self.stats["pool_empty"] += 1
                self.stats["acquired"] += 1

        buffer.seek(0)
        buffer.truncate(0)
        return buffer

    def release(self, buffer: io.BytesIO):
        try:
            buffer.seek(0)
            buffer.truncate(0)
            self.pool.put_nowait(buffer)
            with self.stats_lock:
                self.stats["released"] += 1
        except queue.Full:
            with self.stats_lock:
                self.stats["discarded"] += 1

    def get_stats(self) -> Dict[str, Any]:
        with self.stats_lock:
            return {
                **self.stats.copy(),
                "pool_size": self.pool.qsize(),
                "max_size": self.max_size,
            }


_buffer_pool = None


def get_buffer_pool() -> BufferPool:
    global _buffer_pool
    if _buffer_pool is None:
        _buffer_pool = BufferPool()
    return _buffer_pool


def get_buffer() -> io.BytesIO:
    return get_buffer_pool().acquire()


def put_buffer(buffer: io.BytesIO):
    get_buffer_pool().release(buffer)


# ========== 系统信息收集 ==========
class SystemInfoCollector:
    """系统信息收集器"""

    @staticmethod
    def get_mac_address() -> str:
        try:
            mac = uuid.getnode()
            if (mac >> 40) % 2 == 0:
                return ":".join(("%012X" % mac)[i : i + 2] for i in range(0, 12, 2))
            computer_name = socket.gethostname()
            user_name = os.environ.get("USERNAME", "") or os.environ.get("USER", "")
            unique_str = f"{computer_name}-{user_name}"
            hash_obj = hashlib.md5(unique_str.encode())
            return ":".join(hash_obj.hexdigest()[i : i + 2] for i in range(0, 12, 2))
        except:
            return "00:00:00:00:00:00"

    @staticmethod
    def get_computer_name() -> str:
        try:
            return socket.gethostname()
        except:
            return "UNKNOWN"

    @staticmethod
    def get_ip_address() -> str:
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
    def get_windows_user() -> Optional[str]:
        return os.environ.get("USERNAME") or os.environ.get("USER")

    @staticmethod
    def get_disk_serial() -> Optional[str]:
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
    def get_cpu_id() -> Optional[str]:
        if sys.platform == "win32":
            try:
                import wmi

                c = wmi.WMI()
                for cpu in c.Win32_Processor():
                    return cpu.ProcessorId.strip()
            except:
                pass
        return None

    def get_hardware_fingerprint(self) -> Dict[str, Any]:
        try:
            mac = self.get_mac_address()
            disk = self.get_disk_serial()
            cpu = self.get_cpu_id()

            hardware_parts = []
            if mac and mac != "00:00:00:00:00:00":
                hardware_parts.append(f"mac:{mac}")
            if disk:
                hardware_parts.append(f"disk:{disk}")
            if cpu:
                hardware_parts.append(f"cpu:{cpu}")

            if hardware_parts:
                fingerprint = "|".join(sorted(hardware_parts))
                hash_obj = hashlib.sha256(fingerprint.encode())
                return {
                    "hardware_fingerprint": hash_obj.hexdigest(),
                    "hardware_parts": hardware_parts,
                    "mac_address": mac,
                    "disk_serial": disk,
                    "cpu_id": cpu,
                }
            else:
                return {
                    "hardware_fingerprint": None,
                    "hardware_parts": [],
                    "mac_address": mac,
                    "disk_serial": None,
                    "cpu_id": None,
                }
        except Exception as e:
            logging.getLogger(__name__).error(f"生成硬件指纹失败: {e}")
            return {
                "hardware_fingerprint": None,
                "hardware_parts": [],
                "mac_address": self.get_mac_address(),
                "disk_serial": None,
                "cpu_id": None,
            }

    def get_system_info(self) -> Dict[str, Any]:
        info = {
            "computer_name": self.get_computer_name(),
            "mac_address": self.get_mac_address(),
            "ip_address": self.get_ip_address(),
            "windows_user": self.get_windows_user(),
            "disk_serial": self.get_disk_serial(),
            "cpu_id": self.get_cpu_id(),
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

    def get_system_stats(self) -> Dict[str, Any]:
        if not PSUTIL_AVAILABLE:
            return {}
        try:
            cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "cpu_percent": cpu_percent,
                "cpu_percent_avg": sum(cpu_percent) / len(cpu_percent),
                "memory_percent": memory.percent,
                "memory_used": memory.used,
                "disk_usage": disk.percent,
                "timestamp": datetime.now().isoformat(),
            }
        except:
            return {}


# ========== 配置管理器 ==========
class ConfigManager:
    """配置管理器"""

    CONFIG_VERSION = "4.0.0"

    # 修改：将 DEFAULT_CONFIG 改为方法，延迟导入 Config
    @staticmethod
    def _get_default_config():
        """获取默认配置（延迟导入避免循环依赖）"""
        from client_config import Config

        return {
            "version": ConfigManager.CONFIG_VERSION,
            "server_urls": Config.DEFAULT_SERVERS,
            "interval": Config.SCREENSHOT_INTERVAL,
            "quality": Config.SCREENSHOT_QUALITY,
            "format": Config.SCREENSHOT_FORMAT,
            "client_id": "",
            "employee_id": "",
            "employee_name": "",
            "auto_start": True,
            "hide_window": True,
            "enable_heartbeat": True,
            "enable_batch_upload": True,
            "max_history": Config.MAX_HISTORY,
            "similarity_threshold": Config.SIMILARITY_THRESHOLD,
            "retry_times": Config.RETRY_TIMES,
            "retry_delay": Config.RETRY_DELAY,
            "encryption_enabled": False,
            "last_update": None,
            "enable_browser_monitor": Config.ENABLE_BROWSER_MONITOR,
            "enable_app_monitor": Config.ENABLE_APP_MONITOR,
            "enable_file_monitor": Config.ENABLE_FILE_MONITOR,
            "enable_remote_screen": Config.ENABLE_REMOTE_SCREEN,
            "remote_base_fps": Config.REMOTE_BASE_FPS,
            "remote_min_fps": Config.REMOTE_MIN_FPS,
            "remote_max_fps": Config.REMOTE_MAX_FPS,
            "remote_base_quality": Config.REMOTE_BASE_QUALITY,
            "remote_min_quality": Config.REMOTE_MIN_QUALITY,
            "remote_max_quality": Config.REMOTE_MAX_QUALITY,
            "remote_max_width": Config.REMOTE_MAX_WIDTH,
            "remote_min_width": Config.REMOTE_MIN_WIDTH,
            "remote_enable_diff": Config.REMOTE_ENABLE_DIFF,
            "remote_enable_region": Config.REMOTE_ENABLE_REGION,
            "remote_enable_h264": Config.REMOTE_ENABLE_H264,
            "remote_enable_qr": Config.REMOTE_ENABLE_QR,
        }

    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.DEFAULT_CONFIG = self._get_default_config()  # 改为调用方法
        self.config = self.DEFAULT_CONFIG.copy()
        self.lock = threading.RLock()
        self.last_mtime = 0
        self.load()

    # 以下方法保持不变...
    def load(self) -> bool:
        with self.lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        loaded_config = json.load(f)
                    self.config.update(loaded_config)
                    self.last_mtime = os.path.getmtime(self.config_file)
                    return True
                except Exception as e:
                    print(f"加载配置文件失败: {e}")
            self.save()
            return False

    def save(self) -> bool:
        with self.lock:
            try:
                self.config["version"] = self.CONFIG_VERSION
                self.config["last_update"] = datetime.now().isoformat()
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                self.last_mtime = os.path.getmtime(self.config_file)
                return True
            except Exception as e:
                print(f"保存配置失败: {e}")
                return False

    def get(self, key, default=None):
        with self.lock:
            return self.config.get(key, default)

    def set(self, key, value):
        with self.lock:
            self.config[key] = value
            self.save()

    def update(self, **kwargs):
        with self.lock:
            self.config.update(kwargs)
            self.save()

    def has_changed(self) -> bool:
        if os.path.exists(self.config_file):
            return os.path.getmtime(self.config_file) > self.last_mtime
        return False

    def reload_if_changed(self) -> bool:
        if self.has_changed():
            return self.load()
        return False


# ========== API客户端 ==========
class APIClient:
    """API客户端"""

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
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", False)

        if "files" in kwargs:
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
            # ✅ 添加请求日志
            self.logger.debug(f"POST请求: {url}")
            if "json" in kwargs:
                self.logger.debug(
                    f"请求数据: {json.dumps(kwargs['json'], ensure_ascii=False)[:200]}"
                )

            response = self.session.post(url, **kwargs)

            # ✅ 添加响应日志
            self.logger.info(f"POST {endpoint} 响应状态码: {response.status_code}")

            # 先打印响应内容的前500字符用于调试
            response_text = response.text[:500]
            if response_text:
                self.logger.debug(f"响应内容: {response_text}")

            response.raise_for_status()
            self.error_count = 0
            self.last_error = None

            # ✅ 检查响应内容
            if not response.content:
                self.logger.warning(f"响应内容为空: {url}")
                return None

            # ✅ 尝试解析 JSON
            try:
                result = response.json()
                self.logger.debug(f"JSON解析成功")
                return result
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON解析失败: {e}, 原始响应: {response_text}")
                raise Exception(f"服务器返回非JSON数据: {response_text[:100]}")

        except requests.exceptions.HTTPError as e:
            self.error_count += 1
            self.last_error = str(e)
            try:
                error_detail = response.json().get("detail", str(e))
            except:
                error_detail = response.text or str(e)
            self.logger.error(f"❌ POST失败 {url}: {error_detail}")
            raise Exception(error_detail)
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            self.logger.error(f"❌ POST异常 {url}: {e}")
            raise

    @smart_retry(max_retries=3, base_delay=1, max_delay=10, jitter=2)
    def get(self, endpoint, **kwargs):
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


# ========== 健康监控 ==========
class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthRecord:
    timestamp: float
    component: str
    status: HealthStatus
    message: str = ""
    response_time: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check_time: float = 0.0
    last_healthy_time: float = 0.0
    failure_count: int = 0
    recovery_count: int = 0
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class HealthHistory:
    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self.records = deque(maxlen=max_records)
        self.lock = threading.RLock()

    def add_record(self, record: HealthRecord):
        with self.lock:
            self.records.append(record)

    def get_recent(self, count: int = 10) -> List[HealthRecord]:
        with self.lock:
            return list(self.records)[-count:]

    def get_component_stats(self, component: str, minutes: int = 60) -> Dict[str, Any]:
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
        with self.lock:
            if name not in self.components:
                self.components[name] = ComponentHealth(name=name)
                if recovery_callback:
                    self.recovery_callbacks.setdefault(name, []).append(
                        recovery_callback
                    )
                self.logger.info(f"✅ 组件已注册: {name}")

    def update_status(
        self,
        component: str,
        status: HealthStatus,
        message: str = "",
        response_time: float = 0.0,
        metrics: Dict[str, Any] = None,
    ):
        with self.lock:
            if component not in self.components:
                self.logger.warning(f"尝试更新未注册的组件: {component}")
                return

            comp = self.components[component]
            now = time.time()

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

            record = HealthRecord(
                timestamp=now,
                component=component,
                status=status,
                message=message,
                response_time=response_time,
                details=metrics or {},
            )
            self.history.add_record(record)

            if comp.failure_count >= 3:
                self._trigger_recovery(component)

    def _trigger_recovery(self, component: str):
        now = time.time()
        last_recovery = self.last_recovery_time.get(component, 0)

        if now - last_recovery < self.recovery_cooldown:
            return

        self.last_recovery_time[component] = now
        self.components[component].recovery_count += 1

        self.logger.warning(f"🔄 触发组件恢复: {component}")

        for callback in self.recovery_callbacks.get(component, []):
            try:
                callback()
            except Exception as e:
                self.logger.error(f"恢复回调失败: {e}")

    def get_component_status(self, component: str) -> Optional[ComponentHealth]:
        with self.lock:
            return self.components.get(component)

    def get_all_status(self) -> Dict[str, ComponentHealth]:
        with self.lock:
            return self.components.copy()

    def get_summary(self) -> Dict[str, Any]:
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
        if self.running:
            return
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, name="HealthMonitor", daemon=True
        )
        self.monitor_thread.start()
        self.logger.info("✅ 健康监控已启动")

    def stop_monitoring(self):
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

    def _monitor_loop(self):
        while self.running:
            try:
                now = time.time()
                with self.lock:
                    for name, comp in self.components.items():
                        if now - comp.last_check_time > self.check_interval * 3:
                            self.logger.warning(f"组件 {name} 状态更新超时")
                            comp.status = HealthStatus.UNKNOWN
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"健康监控异常: {e}")
                time.sleep(30)


# ========== 进程看门狗 ==========
class ProcessWatchdog:
    def __init__(self, check_interval: int = 30, max_restarts: int = 5):
        self.check_interval = check_interval
        self.max_restarts = max_restarts
        self.watched_processes: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.running = False
        self.watchdog_thread = None
        self.logger = logging.getLogger(__name__)

        self.stats = {
            "total_restarts": 0,
            "failed_restarts": 0,
            "total_health_check_failures": 0,
            "last_check": None,
        }

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
        with self.lock:
            if name in self.watched_processes:
                self.logger.warning(f"进程 {name} 已存在")
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
            self.logger.info(f"✅ 进程已加入监控: {name}")
            return True

    def start_watch(self, name: str) -> bool:
        with self.lock:
            if name not in self.watched_processes:
                return False

            process_info = self.watched_processes[name]

            if process_info.get("thread") and process_info["thread"].is_alive():
                return True

            if process_info["restart_count"] >= self.max_restarts:
                self.logger.error(f"进程 {name} 已达最大重启次数")
                process_info["status"] = "failed"
                return False

            if process_info["last_restart"] > 0:
                if time.time() - process_info["last_restart"] < 60:
                    return False

            process_info["stop_event"].clear()

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

                self.logger.info(f"🔄 看门狗启动进程: {name}")
                return True

            except Exception as e:
                self.logger.error(f"启动进程 {name} 失败: {e}")
                process_info["status"] = "error"
                process_info["error"] = str(e)
                self.stats["failed_restarts"] += 1
                return False

    def _run_process(self, name: str):
        process_info = self.watched_processes[name]

        try:
            process_info["func"](*process_info["args"], **process_info["kwargs"])
        except Exception as e:
            if process_info["stop_event"].is_set():
                self.logger.info(f"进程 {name} 被停止")
                process_info["status"] = "stopped"
            else:
                self.logger.error(f"进程 {name} 异常退出: {e}")
                process_info["error"] = str(e)
                process_info["status"] = "crashed"

                if process_info["auto_restart"]:
                    self.logger.info(f"⏳ 等待重启进程 {name}")
                    time.sleep(5)
                    self.start_watch(name)
        else:
            process_info["status"] = "stopped"
            self.logger.info(f"进程 {name} 正常退出")

    def heartbeat(self, name: str):
        with self.lock:
            if name in self.watched_processes:
                self.watched_processes[name]["last_heartbeat"] = time.time()
                self.watched_processes[name]["failure_count"] = 0
                self.watched_processes[name]["health_check_failures"] = 0

    def stop_watch(self, name: str):
        with self.lock:
            if name not in self.watched_processes:
                return

            process_info = self.watched_processes[name]
            process_info["auto_restart"] = False
            process_info["status"] = "stopping"
            process_info["stop_event"].set()

            thread = process_info.get("thread")
            if thread and thread.is_alive():
                thread.join(timeout=10)

            process_info["status"] = "stopped"
            process_info["thread"] = None
            process_info["pid"] = None
            self.logger.info(f"⏹️ 看门狗停止进程: {name}")

    def health_check(self, name: str) -> bool:
        with self.lock:
            if name not in self.watched_processes:
                return False

            process_info = self.watched_processes[name]

            thread = process_info.get("thread")
            if not thread or not thread.is_alive():
                return False

            health_check = process_info.get("health_check")
            if health_check:
                try:
                    return health_check()
                except:
                    return False

            return True

    def perform_health_check(self, name: str) -> bool:
        with self.lock:
            if name not in self.watched_processes:
                return False

            process_info = self.watched_processes[name]
            process_info["last_health_check"] = time.time()
            is_healthy = self.health_check(name)

            if not is_healthy:
                process_info["health_check_failures"] += 1
                self.logger.warning(
                    f"⚠️ 进程 {name} 健康检查失败 ({process_info['health_check_failures']}/3)"
                )
                if process_info["health_check_failures"] >= 3:
                    self.logger.error(f"❌ 进程 {name} 连续3次失败，准备重启")
                    self.stats["total_health_check_failures"] += 1
                    self._restart_process(name)
            else:
                if process_info["health_check_failures"] > 0:
                    self.logger.info(f"✅ 进程 {name} 健康恢复")
                process_info["health_check_failures"] = 0

            return is_healthy

    def _restart_process(self, name: str):
        with self.lock:
            if name not in self.watched_processes or not self.running:
                return

            process_info = self.watched_processes[name]

            if not process_info["auto_restart"]:
                return

            if process_info["restart_count"] >= self.max_restarts:
                self.logger.error(f"进程 {name} 已达最大重启次数")
                process_info["status"] = "failed"
                return

            self.logger.info(f"🔄 正在重启进程: {name}")

            old_thread = process_info.get("thread")
            if old_thread and old_thread.is_alive():
                process_info["stop_event"].set()
                old_thread.join(timeout=5)

            process_info["stop_event"].clear()
            process_info["thread"] = None
            process_info["pid"] = None
            process_info["status"] = "stopped"

            self.start_watch(name)
            self.stats["total_restarts"] += 1

    def start(self):
        if self.running:
            return
        self.running = True
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="ProcessWatchdog", daemon=True
        )
        self.watchdog_thread.start()
        self.logger.info("✅ 进程看门狗已启动")

    def stop(self):
        self.logger.info("⏹️ 正在停止看门狗...")
        self.running = False

        if self.watchdog_thread and self.watchdog_thread.is_alive():
            self.watchdog_thread.join(timeout=5)

        with self.lock:
            for name in list(self.watched_processes.keys()):
                self.stop_watch(name)

        self.logger.info("⏹️ 进程看门狗已停止")

    def get_status(self) -> Dict[str, Any]:
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

    def report_failure(self, name: str, error: str = ""):
        with self.lock:
            if name in self.watched_processes:
                self.watched_processes[name]["failure_count"] += 1
                self.watched_processes[name]["last_error"] = error
                self.watched_processes[name]["last_failure"] = time.time()
                if self.watched_processes[name]["failure_count"] >= 3:
                    self.logger.warning(f"组件 {name} 连续失败3次")
                    self._restart_process(name)

    def _watchdog_loop(self):
        while self.running:
            try:
                self.stats["last_check"] = time.time()
                now = time.time()

                with self.lock:
                    for name, process_info in list(self.watched_processes.items()):
                        if not process_info["auto_restart"]:
                            continue

                        thread = process_info.get("thread")

                        if not thread or not thread.is_alive():
                            self.logger.warning(f"⚠️ 进程 {name} 已停止，准备重启")
                            self._restart_process(name)
                            continue

                        health_check = process_info.get("health_check")
                        health_check_interval = process_info.get(
                            "health_check_interval", 60
                        )
                        last_health_check = process_info.get("last_health_check", 0)

                        if health_check and (
                            now - last_health_check >= health_check_interval
                        ):
                            threading.Thread(
                                target=self.perform_health_check,
                                args=(name,),
                                daemon=True,
                            ).start()

                time.sleep(self.check_interval)

            except Exception as e:
                self.logger.error(f"看门狗异常: {e}")
                time.sleep(30)


# ========== 感知哈希 ==========
class PerceptualHash:
    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold
        self.has_imagehash = IMAGEHASH_AVAILABLE
        self.logger = logging.getLogger(__name__)
        self.cache = {}
        self.cache_lock = threading.RLock()

        if self.has_imagehash:
            self.logger.info("✅ 已启用感知哈希检测")
        else:
            self.logger.warning("⚠️ imagehash未安装，使用MD5检测")

    def are_similar(self, img1_path: str, img2_path: str) -> bool:
        if not os.path.exists(img1_path) or not os.path.exists(img2_path):
            return False

        try:
            size1 = os.path.getsize(img1_path)
            size2 = os.path.getsize(img2_path)
            if abs(size1 - size2) / max(size1, size2) > 0.3:
                return False

            if self.has_imagehash:
                similarity = self._compare_with_phash(img1_path, img2_path)
                if similarity is not None:
                    return similarity >= self.threshold

            return self._compare_with_md5(img1_path, img2_path)

        except Exception as e:
            self.logger.debug(f"相似度检测失败: {e}")
            return False

    def _compare_with_phash(self, img1_path: str, img2_path: str) -> Optional[float]:
        try:
            hash1 = self._get_phash(img1_path)
            hash2 = self._get_phash(img2_path)

            if hash1 is None or hash2 is None:
                return None

            distance = hash1 - hash2
            similarity = 1 - (distance / 64)
            return similarity

        except Exception as e:
            self.logger.debug(f"感知哈希比较失败: {e}")
            return None

    def _get_phash(self, image_path: str):
        with self.cache_lock:
            if image_path in self.cache:
                return self.cache[image_path]

            try:
                img = Image.open(image_path).convert("L")
                img = img.resize((64, 64), Image.Resampling.LANCZOS)

                # 修复：检查 imagehash 是否可用
                if IMAGEHASH_AVAILABLE:
                    phash = imagehash.phash(img)
                else:
                    # 降级处理：返回None，让调用者使用MD5
                    return None

                self.cache[image_path] = phash

                if len(self.cache) > 100:
                    for key in list(self.cache.keys())[:50]:
                        del self.cache[key]

                return phash

            except Exception as e:
                self.logger.debug(f"计算感知哈希失败: {e}")
                return None

    def _compare_with_md5(self, img1_path: str, img2_path: str) -> bool:
        try:
            hash1 = hashlib.md5(open(img1_path, "rb").read()).hexdigest()
            hash2 = hashlib.md5(open(img2_path, "rb").read()).hexdigest()
            return hash1 == hash2
        except:
            return False


# ========== 多显示器截图 ==========
class MultiMonitorScreenshot:
    def __init__(self):
        self.has_mss = MSS_AVAILABLE
        self.logger = logging.getLogger(__name__)

        if self.has_mss:
            self.logger.info("✅ 已启用多显示器截图支持")
        else:
            self.logger.warning("⚠️ mss未安装，使用单显示器模式")

    def capture_all_monitors(self) -> Optional[Image.Image]:
        if self.has_mss:
            return self._capture_with_mss()
        else:
            return self._capture_with_pil()

    def _capture_with_mss(self) -> Optional[Image.Image]:
        try:
            with mss.mss() as sct:
                monitors = sct.monitors[1:]
                if not monitors:
                    self.logger.warning("未检测到显示器")
                    return None

                total_width = sum(m["width"] for m in monitors)
                max_height = max(m["height"] for m in monitors)
                merged = Image.new("RGB", (total_width, max_height))

                x_offset = 0
                for i, monitor in enumerate(monitors):
                    screenshot = sct.grab(monitor)
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                    merged.paste(img, (x_offset, 0))
                    x_offset += monitor["width"]

                self.logger.info(
                    f"✅ 多显示器截图成功: {total_width}x{max_height} ({len(monitors)}个)"
                )
                return merged

        except Exception as e:
            self.logger.error(f"mss截图失败: {e}")
            return self._capture_with_pil()

    def _capture_with_pil(self) -> Optional[Image.Image]:
        try:
            screenshot = ImageGrab.grab(all_screens=True)
            self.logger.info(
                f"✅ PIL截图成功: {screenshot.size[0]}x{screenshot.size[1]}"
            )
            return screenshot
        except Exception as e:
            self.logger.error(f"PIL截图失败: {e}")
            return None


# ========== 上传任务 ==========
@dataclass
class UploadTask:
    image_data: bytes
    filename: str
    employee_id: str
    client_id: str
    timestamp: str
    computer_name: str
    windows_user: str
    format: str
    encrypted: bool = False
    retry_count: int = 0
    last_attempt: float = 0.0


# ========== 上传队列 ==========
class UploadQueue:
    def __init__(
        self,
        client,
        max_queue_size: int = 100,
        worker_count: int = 3,
        cache_dir: str = "cache",
        max_cache_size: int = 500 * 1024 * 1024,
    ):
        self.client = client
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.workers = []
        self.running = False
        self.logger = logging.getLogger(__name__)
        self.lock = threading.RLock()

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

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.max_cache_size = max_cache_size
        self.worker_count = worker_count
        self.base_delay = 5
        self.max_delay = 120

    def start(self):
        if self.running:
            return

        self.running = True

        for i in range(self.worker_count):
            worker = threading.Thread(
                target=self._worker_loop, name=f"UploadWorker-{i}", daemon=True
            )
            worker.start()
            self.workers.append(worker)

        self._load_cached_tasks()
        self.logger.info(f"✅ 上传队列已启动 (工作线程: {self.worker_count})")

    def stop(self):
        self.running = False
        waited = 0
        max_wait = 10

        while not self.queue.empty() and waited < max_wait:
            time.sleep(1)
            waited += 1

        if not self.queue.empty():
            self.logger.warning(f"队列还有 {self.queue.qsize()} 个任务未处理")

    def enqueue(self, task: UploadTask) -> bool:
        try:
            self.queue.put_nowait(task)
            with self.lock:
                self.stats["enqueued"] += 1
            return True
        except queue.Full:
            self._save_to_cache(task)
            with self.lock:
                self.stats["queue_full"] += 1
                self.stats["cache_saved"] += 1
            return False

    def _worker_loop(self):
        while self.running:
            try:
                try:
                    task = self.queue.get(timeout=1)
                except queue.Empty:
                    continue

                self._process_task(task)
                self.queue.task_done()

            except Exception as e:
                self.logger.error(f"工作线程异常: {e}")
                time.sleep(1)

    def _process_task(self, task: UploadTask):
        try:
            if task.retry_count > 0:
                delay = min(
                    self.base_delay * (2 ** (task.retry_count - 1)), self.max_delay
                )
                delay += random.uniform(0, 5)

                if time.time() - task.last_attempt < delay:
                    self.enqueue(task)
                    return

            task.last_attempt = time.time()
            success = self._upload_task(task)

            if success:
                with self.lock:
                    self.stats["processed"] += 1
                self.logger.debug(f"✅ 上传成功: {task.filename}")
            else:
                task.retry_count += 1

                if task.retry_count < self.client.retry_times:
                    with self.lock:
                        self.stats["retried"] += 1
                    self.enqueue(task)
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
        try:
            files = {
                "file": (
                    task.filename,
                    io.BytesIO(task.image_data),
                    f"image/{task.format}",
                )
            }
            data = {
                "employee_id": task.employee_id,
                "client_id": task.client_id,
                "timestamp": task.timestamp,
                "computer_name": task.computer_name,
                "windows_user": task.windows_user,
                "encrypted": str(task.encrypted).lower(),
                "format": task.format,
            }

            response = self.client.api_client.session.post(
                f"{self.client.current_server}/api/upload",
                files=files,
                data=data,
                timeout=60,
            )

            return response.status_code == 200

        except Exception as e:
            self.logger.debug(f"上传异常: {e}")
            return False

    def _save_to_cache(self, task: UploadTask):
        try:
            cache_file = self.cache_dir / task.filename
            AtomicFileOperation.atomic_write(str(cache_file), task.image_data)
            self._cleanup_cache()
        except Exception as e:
            self.logger.error(f"保存到缓存失败: {e}")

    def _load_cached_tasks(self):
        try:
            count = 0
            for cache_file in self.cache_dir.glob("screenshot_*"):
                if cache_file.stat().st_size == 0:
                    AtomicFileOperation.atomic_delete(str(cache_file))
                    continue

                try:
                    image_data = AtomicFileOperation.atomic_read(str(cache_file))
                    if image_data is None:
                        continue

                    parts = cache_file.stem.split("_")
                    if len(parts) < 2:
                        continue

                    encrypted = "encrypted" in cache_file.suffixes

                    task = UploadTask(
                        image_data=image_data,
                        filename=cache_file.name,
                        employee_id=self.client.employee_id,
                        client_id=self.client.client_id,
                        timestamp=parts[1] + "_" + parts[2] if len(parts) > 2 else "",
                        computer_name=self.client.system_info.get_computer_name(),
                        windows_user=self.client.system_info.get_windows_user(),
                        format=cache_file.suffix[1:] or "webp",
                        encrypted=encrypted,
                    )

                    self.enqueue(task)
                    count += 1
                    AtomicFileOperation.atomic_delete(str(cache_file))

                except Exception as e:
                    self.logger.error(f"加载缓存失败 {cache_file}: {e}")

            if count > 0:
                self.logger.info(f"📦 从缓存加载了 {count} 个任务")
                with self.lock:
                    self.stats["cache_loaded"] = count

        except Exception as e:
            self.logger.error(f"加载缓存失败: {e}")

    def _cleanup_cache(self):
        try:
            total_size = 0
            files = []

            for cache_file in self.cache_dir.glob("*"):
                if cache_file.is_file() and not cache_file.name.startswith(".tmp_"):
                    size = cache_file.stat().st_size
                    total_size += size
                    files.append((cache_file, cache_file.stat().st_mtime, size))

            if total_size > self.max_cache_size:
                files.sort(key=lambda x: x[1])
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
                    f"🧹 缓存清理: 删除 {deleted_count} 个，释放 {deleted_size/1024/1024:.1f}MB"
                )

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
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
