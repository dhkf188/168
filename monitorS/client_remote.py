#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client_remote.py - 企业级远程屏幕采集模块（完美契合后端）
功能：
- 屏幕采集与压缩
- 动态帧率/画质控制
- 差异帧传输（只传变化区域）
- 区域编码（ROI检测）
- H.264硬件加速
- 弱网自适应
- 二维码检测
- 窗口排除功能
- 资源池化管理
- 异常恢复机制
"""

import asyncio
import base64
import io
import json
import logging
import threading
import time
import zlib
import gc
import hashlib
import sys
import os
from typing import Optional, Dict, Any, List, Tuple, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import queue
import math
import socket
import weakref
from collections import deque

import websockets
from PIL import Image

try:
    import mss
    import mss.tools

    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    import cv2
    import numpy as np

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# try:
#     import pyzbar.pyzbar as pyzbar

#     ZBAR_AVAILABLE = True
# except ImportError:
#     ZBAR_AVAILABLE = False
ZBAR_AVAILABLE = False

try:
    from PIL import ImageGrab

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# 尝试导入窗口管理库
try:
    import win32gui
    import win32con
    import win32api

    WINDOWS_AVAILABLE = sys.platform == "win32"
except ImportError:
    WINDOWS_AVAILABLE = False

try:
    import Xlib.display
    import Xlib.X

    LINUX_AVAILABLE = sys.platform.startswith("linux")
except ImportError:
    LINUX_AVAILABLE = False


class FrameType(Enum):
    """帧类型枚举"""

    FULL = "full_frame"
    DIFF = "diff_frame"
    REGION = "region_frame"


class ConnectionState(Enum):
    """连接状态枚举"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"


@dataclass
class RemoteScreenConfig:
    """企业级远程屏幕配置"""

    # 基础设置
    server_url: str = ""
    client_id: str = ""
    employee_id: str = ""

    # 初始质量设置
    initial_quality: int = 80
    initial_fps: int = 5

    # 动态调整范围
    min_quality: int = 30
    max_quality: int = 95
    min_fps: int = 1
    max_fps: int = 10

    # 分辨率设置
    max_width: int = 1280
    min_width: int = 640

    # 弱网检测
    network_check_interval: int = 5
    latency_threshold_high: float = 500
    latency_threshold_low: float = 100

    # 高级优化
    enable_diff_frame: bool = True
    enable_region_detect: bool = True
    enable_h264: bool = CV2_AVAILABLE
    enable_qr_detect: bool = False
    diff_area_threshold: int = 1000
    region_area_threshold: int = 5000
    merge_distance: int = 50

    # ===== 窗口排除设置（增强版）=====
    enable_window_exclusion: bool = False  # 窗口排除功能开关
    excluded_windows: List[str] = field(default_factory=list)  # 手动排除的窗口标题列表
    excluded_processes: List[str] = field(default_factory=list)  # 手动排除的进程名列表
    auto_exclude_sensitive: bool = True  # 自动排除敏感窗口（任务管理器、注册表等）
    exclude_fullscreen: bool = False  # 排除全屏应用（游戏、视频播放器等）
    exclusion_update_interval: int = 5  # 窗口列表更新间隔（秒）

    # ===== 敏感窗口关键词（用于自动排除）=====
    sensitive_window_keywords: List[str] = field(
        default_factory=lambda: [
            "task manager",
            "任务管理器",
            "registry",
            "注册表编辑器",
            "regedit",
            "cmd",
            "命令提示符",
            "command prompt",
            "powershell",
            "windows powershell",
            "process explorer",
            "进程管理器",
            "process monitor",
            "security",
            "安全中心",
            "windows security",
            "event viewer",
            "事件查看器",
            "local security policy",
            "本地安全策略",
            "group policy",
            "组策略管理",
            "gpedit",
            "services",
            "服务",
            "device manager",
            "设备管理器",
            "disk management",
            "磁盘管理",
            "computer management",
            "计算机管理",
            "registry editor",
            "注册表编辑器",
        ]
    )

    sensitive_process_keywords: List[str] = field(
        default_factory=lambda: [
            "taskmgr.exe",
            "regedit.exe",
            "cmd.exe",
            "powershell.exe",
            "procexp.exe",
            "procmon.exe",
            "regmon.exe",
            "filemon.exe",
            "mmc.exe",
            "control.exe",
            "secpol.msc",
            "gpedit.msc",
            "eventvwr.exe",
            "services.msc",
            "compmgmt.msc",
            "diskmgmt.msc",
            "devmgmt.msc",
            "certmgr.msc",
            "azman.msc",
            "fsmgmt.msc",
        ]
    )

    # ===== 网络配置（增强版）=====
    network_check_interval: int = 5  # 网络检测间隔（秒）
    latency_threshold_high: float = 500  # 高延迟阈值（ms）
    latency_threshold_low: float = 100  # 低延迟阈值（ms）
    bandwidth_limit: int = 0  # 带宽限制（KB/s），0表示不限制
    jitter_threshold: float = 50  # 抖动阈值（ms）

    # ===== 编码配置（增强版）=====
    diff_area_threshold: int = 1000  # 差异区域最小像素
    region_area_threshold: int = 5000  # 活动区域最小像素
    merge_distance: int = 50  # 区域合并距离（像素）
    motion_detection_sensitivity: int = 30  # 运动检测灵敏度（0-255）
    background_update_rate: float = 0.1  # 背景更新率（0-1）

    # ===== 资源管理（增强版）=====
    max_frame_queue_size: int = 5  # 最大帧队列大小
    frame_buffer_size: int = 3  # 帧缓冲区大小
    encode_pool_size: int = 2  # 编码工作池大小
    memory_limit_mb: int = 512  # 内存限制（MB）
    cpu_limit_percent: int = 50  # CPU使用率限制（%）

    # WebSocket设置
    ws_ping_interval: int = 20
    ws_ping_timeout: int = 10
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 5
    connection_timeout: int = 15

    # 性能监控
    enable_performance_monitor: bool = True
    stats_report_interval: int = 10
    enable_detailed_logging: bool = False  # 启用详细日志
    metrics_history_size: int = 100  # 指标历史记录大小


@dataclass
class NetworkStats:
    """网络统计信息"""

    last_frame_time: float = 0
    frame_sent_times: deque = field(default_factory=lambda: deque(maxlen=50))
    round_trip_times: deque = field(default_factory=lambda: deque(maxlen=20))
    bytes_sent: int = 0
    frames_sent: int = 0
    network_quality: int = 100
    avg_frame_size: float = 0
    diff_ratio: float = 0
    region_ratio: float = 0
    encode_times: deque = field(default_factory=lambda: deque(maxlen=20))
    dropped_frames: int = 0
    reconnect_count: int = 0
    last_error: Optional[str] = None
    error_count: int = 0


@dataclass
class PerformanceMetrics:
    """性能指标"""

    fps_actual: float = 0.0
    fps_target: float = 0.0
    encode_time_ms: float = 0.0
    capture_time_ms: float = 0.0
    transmission_time_ms: float = 0.0
    cpu_usage: float = 0.0
    memory_usage_mb: float = 0.0
    frame_skip_ratio: float = 0.0
    exclusion_time_ms: float = 0.0
    last_update: float = field(default_factory=time.time)


@dataclass
class WindowInfo:
    """窗口信息"""

    hwnd: int = 0
    title: str = ""
    process_name: str = ""
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
    is_visible: bool = False


class WindowExclusionManager:
    """窗口排除管理器"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._excluded_windows: Set[str] = set()
        self._excluded_processes: Set[str] = set()
        self._window_cache: Dict[int, WindowInfo] = {}
        self._cache_timeout = 2.0  # 缓存超时时间
        self._last_cache_time = 0
        self._lock = threading.RLock()

    def update_exclusions(
        self, excluded_windows: List[str], excluded_processes: List[str]
    ):
        """更新排除列表"""
        with self._lock:
            self._excluded_windows = set(excluded_windows)
            self._excluded_processes = set(excluded_processes)
            self.logger.info(
                f"窗口排除已更新: windows={len(self._excluded_windows)}, processes={len(self._excluded_processes)}"
            )

    def get_excluded_regions(self) -> List[Tuple[int, int, int, int]]:
        """获取需要排除的窗口区域"""
        if not self._excluded_windows and not self._excluded_processes:
            return []

        try:
            regions = []
            windows = self._get_visible_windows()

            for window in windows:
                if self._should_exclude_window(window):
                    x, y, w, h = window.rect
                    if w > 0 and h > 0:
                        regions.append((x, y, w, h))
                        self.logger.debug(
                            f"排除窗口: {window.title[:50]}, 区域: ({x}, {y}, {w}, {h})"
                        )

            return regions

        except Exception as e:
            self.logger.error(f"获取排除区域失败: {e}")
            return []

    def _get_visible_windows(self) -> List[WindowInfo]:
        """获取所有可见窗口"""
        current_time = time.time()

        # 检查缓存是否过期
        with self._lock:
            if current_time - self._last_cache_time < self._cache_timeout:
                return list(self._window_cache.values())

        windows = []

        if WINDOWS_AVAILABLE:
            windows = self._get_windows_windows()
        elif LINUX_AVAILABLE:
            windows = self._get_windows_linux()

        # 更新缓存
        with self._lock:
            self._window_cache.clear()
            for window in windows:
                self._window_cache[window.hwnd] = window
            self._last_cache_time = current_time

        return windows

    def _get_windows_windows(self) -> List[WindowInfo]:
        """Windows平台获取窗口列表"""
        windows = []

        def enum_callback(hwnd, windows_list):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    title = win32gui.GetWindowText(hwnd)
                    if title:  # 只获取有标题的窗口
                        rect = win32gui.GetWindowRect(hwnd)
                        x, y, right, bottom = rect
                        width = right - x
                        height = bottom - y

                        # 获取进程名
                        try:
                            _, pid = win32gui.GetWindowThreadProcessId(hwnd)
                            process_handle = win32api.OpenProcess(0x0400, False, pid)
                            process_name = win32gui.GetModuleFileNameEx(
                                process_handle, 0
                            )
                            process_name = os.path.basename(process_name)
                            win32api.CloseHandle(process_handle)
                        except:
                            process_name = ""

                        windows.append(
                            WindowInfo(
                                hwnd=hwnd,
                                title=title,
                                process_name=process_name,
                                rect=(x, y, width, height),
                                is_visible=True,
                            )
                        )
                except:
                    pass

        try:
            win32gui.EnumWindows(enum_callback, windows)
        except Exception as e:
            self.logger.error(f"枚举Windows窗口失败: {e}")

        return windows

    def _get_windows_linux(self) -> List[WindowInfo]:
        """Linux平台获取窗口列表"""
        windows = []
        try:
            display = Xlib.display.Display()
            root = display.screen().root

            # 获取所有窗口
            window_ids = root.get_full_property(
                display.intern_atom("_NET_CLIENT_LIST"), Xlib.X.AnyPropertyType
            )

            if window_ids:
                for wid in window_ids.value:
                    try:
                        window = display.create_resource_object("window", wid)

                        # 获取窗口属性
                        name = window.get_wm_name()
                        if name:
                            # 获取窗口几何信息
                            geometry = window.get_geometry()
                            x, y = window.get_position()

                            windows.append(
                                WindowInfo(
                                    hwnd=wid,
                                    title=name or "",
                                    process_name="",  # Linux下获取进程名较复杂
                                    rect=(x, y, geometry.width, geometry.height),
                                    is_visible=True,
                                )
                            )
                    except:
                        pass

            display.close()

        except Exception as e:
            self.logger.error(f"枚举Linux窗口失败: {e}")

        return windows

    def _should_exclude_window(self, window: WindowInfo) -> bool:
        """判断窗口是否应该排除"""
        # 检查标题
        for excluded in self._excluded_windows:
            if excluded.lower() in window.title.lower():
                return True

        # 检查进程名
        for excluded in self._excluded_processes:
            if excluded.lower() in window.process_name.lower():
                return True

        return False

    def clear_cache(self):
        """清空缓存"""
        with self._lock:
            self._window_cache.clear()
            self._last_cache_time = 0


class FrameBuffer:
    """帧缓冲区 - 管理待发送帧"""

    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._last_frame_hash: Optional[str] = None

    def put(self, frame_data: Dict[str, Any]) -> bool:
        """放入帧数据"""
        with self._lock:
            frame_hash = hashlib.md5(
                str(frame_data.get("timestamp", "")).encode()
            ).hexdigest()

            if frame_hash == self._last_frame_hash:
                return False

            self._last_frame_hash = frame_hash
            self._buffer.append(frame_data)
            return True

    def get(self) -> Optional[Dict[str, Any]]:
        """获取帧数据"""
        with self._lock:
            return self._buffer.popleft() if self._buffer else None

    def clear(self):
        """清空缓冲区"""
        with self._lock:
            self._buffer.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def is_full(self) -> bool:
        with self._lock:
            return len(self._buffer) >= self.max_size

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._buffer) == 0


class EncodeWorker:
    """编码工作器 - 异步编码处理"""

    def __init__(self, worker_id: int, parent_ref: weakref.ref):
        self.worker_id = worker_id
        self.parent_ref = parent_ref
        self.logger = logging.getLogger(f"{__name__}.EncodeWorker.{worker_id}")
        self.running = True
        self.task_queue: queue.Queue = queue.Queue(maxsize=10)
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """启动工作器"""
        self.thread = threading.Thread(
            target=self._run, name=f"EncodeWorker-{self.worker_id}", daemon=True
        )
        self.thread.start()
        self.logger.info(f"编码工作器 {self.worker_id} 已启动")

    def stop(self):
        """停止工作器"""
        self.running = False
        try:
            self.task_queue.put(None, timeout=1)
        except queue.Full:
            pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)

    def submit(
        self, frame: np.ndarray, frame_type: FrameType, callback: Callable
    ) -> bool:
        """提交编码任务"""
        try:
            if self.task_queue.full():
                self.logger.warning(f"工作器 {self.worker_id} 任务队列已满，丢弃帧")
                return False
            self.task_queue.put((frame.copy(), frame_type, callback), timeout=0.1)
            return True
        except queue.Full:
            return False

    def _run(self):
        """工作器主循环"""
        while self.running:
            try:
                item = self.task_queue.get(timeout=1.0)
                if item is None:
                    break

                frame, frame_type, callback = item
                encoded_data = self._encode_frame(frame, frame_type)

                if encoded_data and callback:
                    try:
                        callback(encoded_data)
                    except Exception as e:
                        self.logger.error(f"回调执行失败: {e}")

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"编码失败: {e}")

    def _encode_frame(
        self, frame: np.ndarray, frame_type: FrameType
    ) -> Optional[bytes]:
        """编码帧"""
        parent = self.parent_ref()
        if not parent:
            return None

        try:
            quality = parent._get_target_quality()

            if frame_type == FrameType.FULL:
                return parent._encode_full_frame_sync(frame, quality)
            elif frame_type == FrameType.DIFF:
                return parent._encode_diff_frame_sync(frame, quality)
            elif frame_type == FrameType.REGION:
                return parent._encode_region_frame_sync(frame, quality)

        except Exception as e:
            self.logger.error(f"编码异常: {e}")
            return None


class BandwidthEstimator:
    """带宽估算器 - 增强版"""

    def __init__(self, alpha=0.7):
        self.samples = deque(maxlen=30)
        self.last_sample_time = 0
        self.last_bytes = 0
        self.alpha = alpha
        self.estimated_bw = 10 * 1024 * 1024  # 默认10Mbps

    def update(self, bytes_delta: int, timestamp: float):
        """
        更新带宽估算
        bytes_delta: 自上次更新以来的字节数增量
        timestamp: 当前时间戳
        """
        if self.last_sample_time > 0:
            elapsed = timestamp - self.last_sample_time
            if elapsed > 0.1:  # 至少100ms间隔
                # 计算瞬时带宽 (bps)
                bps = bytes_delta * 8 / elapsed
                # 限制合理范围 100Kbps - 100Mbps
                bps = max(100 * 1024, min(100 * 1024 * 1024, bps))
                self.samples.append(bps)

                # EWMA 平滑
                if len(self.samples) > 1:
                    self.estimated_bw = (
                        self.alpha * bps + (1 - self.alpha) * self.estimated_bw
                    )

        self.last_sample_time = timestamp
        self.last_bytes += bytes_delta  # 累计字节（可选，用于调试）

    def get_bandwidth(self) -> float:
        """获取估算带宽 (bps)"""
        if self.samples:
            recent = list(self.samples)[-5:]
            if recent:
                sorted_recent = sorted(recent)
                return sorted_recent[len(sorted_recent) // 2]
        return self.estimated_bw

    def get_bandwidth_kbps(self) -> float:
        """获取带宽 (Kbps)"""
        return self.get_bandwidth() / 1024

    def get_bandwidth_mbps(self) -> float:
        """获取带宽 (Mbps)"""
        return self.get_bandwidth() / (1024 * 1024)


# 在 BandwidthEstimator 类之后添加
class KeyFrameManager:
    """关键帧管理器"""

    def __init__(self):
        self.last_keyframe_time = 0
        self.keyframe_interval = 5.0  # 每5秒强制发一次完整帧
        self.motion_buffer = deque(maxlen=10)

    def should_send_keyframe(self, diff_ratio: float, now: float) -> bool:
        """判断是否需要发送关键帧"""
        # 定时刷新
        if now - self.last_keyframe_time > self.keyframe_interval:
            return True

        # 剧烈变化
        if diff_ratio > 0.8:
            return True

        # 累积变化检测
        self.motion_buffer.append(diff_ratio)
        if len(self.motion_buffer) == self.motion_buffer.maxlen:
            avg_motion = sum(self.motion_buffer) / len(self.motion_buffer)
            if avg_motion > 0.3:
                return True

        return False

    def mark_keyframe_sent(self, now: float):
        self.last_keyframe_time = now
        self.motion_buffer.clear()


class RemoteScreenManager:
    """
    企业级远程屏幕管理器
    - 窗口排除功能
    - 修复递归循环问题
    - 资源池化管理
    - 完善的异常恢复
    """

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        # 配置
        self.config = self._load_config()

        # 状态管理
        self.state = ConnectionState.DISCONNECTED
        self.running = False
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

        # 会话信息
        self.session_id: Optional[str] = None
        self.viewer_count = 0
        self.reconnect_attempts = 0
        self._pending_start = False

        # 动态参数
        self.current_quality = self.config.initial_quality
        self.current_fps = self.config.initial_fps
        self.current_width = self.config.max_width

        # 帧缓存
        self._frame_buffer = FrameBuffer(self.config.frame_buffer_size)
        self._last_frame: Optional[np.ndarray] = None
        self._last_motion_frame: Optional[np.ndarray] = None
        self._active_regions: List[Tuple[int, int, int, int]] = []
        self._excluded_regions: List[Tuple[int, int, int, int]] = []
        self._last_diff_ratio = 1.0

        # 窗口排除管理器
        self._window_exclusion_manager = WindowExclusionManager(self.logger)
        self._last_send_time = 0
        self._frame_processing = False
        self._last_frame_time = 0

        # ✅ 生产者-消费者模式变量（延迟初始化，在事件循环中创建）
        self._latest_frame = None
        self._frame_ready_event = None  # 稍后在 _async_capture_loop 中创建
        self._frames_dropped = 0

        # 网络统计
        self.network_stats = NetworkStats()
        self.performance_metrics = PerformanceMetrics()

        self.bandwidth_estimator = BandwidthEstimator()

        # WebSocket
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_lock = asyncio.Lock()

        # 异步任务管理
        self._tasks: Set[asyncio.Task] = set()
        self._message_queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # 编码工作池
        self._encode_workers: List[EncodeWorker] = []
        self._init_encode_pool()

        # 后台线程
        self._capture_thread: Optional[threading.Thread] = None
        self._stats_thread: Optional[threading.Thread] = None

        # 帧发送回调
        self._frame_callback: Optional[Callable] = None

        # 性能计数器
        self._frame_counter = 0
        self._last_frame_time = 0
        self._frame_skip_counter = 0

        self.logger.info("=" * 60)
        self.logger.info("企业级远程屏幕管理器已初始化")
        self.logger.info(f"客户端ID: {self.config.client_id}")
        self.logger.info(f"服务器: {self.config.server_url}")
        self.logger.info(f"OpenCV可用: {CV2_AVAILABLE}")
        self.logger.info(f"MSS可用: {MSS_AVAILABLE}")
        self.logger.info(f"窗口排除: {self.config.enable_window_exclusion}")
        self.logger.info("=" * 60)
        self.keyframe_manager = KeyFrameManager()

    def _load_config(self) -> RemoteScreenConfig:
        """加载配置"""
        config_mgr = (
            self.client.config_manager
            if hasattr(self.client, "config_manager")
            else None
        )

        if config_mgr:
            return RemoteScreenConfig(
                server_url=(
                    self.client.current_server
                    if hasattr(self.client, "current_server")
                    else ""
                ),
                client_id=(
                    self.client.client_id if hasattr(self.client, "client_id") else ""
                ),
                employee_id=(
                    self.client.employee_id
                    if hasattr(self.client, "employee_id")
                    else ""
                ),
                # 帧率配置
                initial_fps=config_mgr.get("remote_base_fps", 5),
                min_fps=config_mgr.get("remote_min_fps", 1),
                max_fps=config_mgr.get("remote_max_fps", 10),
                # 画质配置
                initial_quality=config_mgr.get("remote_base_quality", 70),
                min_quality=config_mgr.get("remote_min_quality", 30),
                max_quality=config_mgr.get("remote_max_quality", 85),
                # 分辨率配置
                max_width=config_mgr.get("remote_max_width", 1280),
                min_width=config_mgr.get("remote_min_width", 640),
                # 高级优化
                enable_diff_frame=config_mgr.get("remote_enable_diff", True),
                enable_region_detect=config_mgr.get("remote_enable_region", True),
                enable_h264=config_mgr.get("remote_enable_h264", True)
                and CV2_AVAILABLE,
                enable_qr_detect=config_mgr.get("remote_enable_qr", False)
                and ZBAR_AVAILABLE,
                # 窗口排除配置（新增）
                enable_window_exclusion=config_mgr.get(
                    "remote_enable_window_exclusion", False
                ),
                excluded_windows=config_mgr.get("remote_excluded_windows", []),
                excluded_processes=config_mgr.get("remote_excluded_processes", []),
                auto_exclude_sensitive=config_mgr.get(
                    "remote_auto_exclude_sensitive", True
                ),
                exclude_fullscreen=config_mgr.get("remote_exclude_fullscreen", False),
                exclusion_update_interval=config_mgr.get(
                    "remote_exclusion_update_interval", 5
                ),
                # 网络配置（新增）
                network_check_interval=config_mgr.get(
                    "remote_network_check_interval", 5
                ),
                latency_threshold_high=config_mgr.get(
                    "remote_latency_threshold_high", 500
                ),
                latency_threshold_low=config_mgr.get(
                    "remote_latency_threshold_low", 100
                ),
                # 编码配置（新增）
                diff_area_threshold=config_mgr.get("remote_diff_area_threshold", 1000),
                region_area_threshold=config_mgr.get(
                    "remote_region_area_threshold", 5000
                ),
                merge_distance=config_mgr.get("remote_merge_distance", 50),
                # 资源管理配置（新增）
                encode_pool_size=config_mgr.get("remote_encode_pool_size", 2),
                frame_buffer_size=config_mgr.get("remote_frame_buffer_size", 3),
                stats_report_interval=config_mgr.get(
                    "remote_stats_report_interval", 10
                ),
            )
        else:
            return RemoteScreenConfig(
                server_url=getattr(self.client, "current_server", ""),
                client_id=getattr(self.client, "client_id", ""),
                employee_id=getattr(self.client, "employee_id", ""),
            )

    def _init_encode_pool(self):
        """初始化编码工作池"""
        for i in range(self.config.encode_pool_size):
            worker = EncodeWorker(i, weakref.ref(self))
            worker.start()
            self._encode_workers.append(worker)

    def start(self):
        """启动远程屏幕服务"""
        with self._lock:
            if self.running:
                self.logger.debug("远程屏幕服务已在运行")
                return

            if not self.config.client_id:
                self.logger.warning("client_id 为空，远程屏幕服务将在注册后自动启动")
                self._pending_start = True
                return

            if not self.config.server_url:
                self.logger.error("服务器URL为空，无法启动远程屏幕")
                return

            self.running = True
            self._stop_event.clear()

            # 初始化窗口排除管理器
            if self.config.enable_window_exclusion:
                self._window_exclusion_manager.update_exclusions(
                    self.config.excluded_windows, self.config.excluded_processes
                )

            self.logger.info("=" * 60)
            self.logger.info("启动远程屏幕服务")
            self.logger.info(f"客户端ID: {self.config.client_id}")
            self.logger.info(f"服务器: {self.config.server_url}")
            self.logger.info(f"初始帧率: {self.current_fps}")
            self.logger.info(f"初始质量: {self.current_quality}")
            self.logger.info(f"窗口排除: {self.config.enable_window_exclusion}")
            if self.config.enable_window_exclusion:
                self.logger.info(f"排除窗口: {self.config.excluded_windows}")
                self.logger.info(f"排除进程: {self.config.excluded_processes}")
            self.logger.info("=" * 60)

            # 启动采集线程
            self._capture_thread = threading.Thread(
                target=self._run_capture_loop, name="RemoteScreenCapture", daemon=True
            )
            self._capture_thread.start()

            # 启动统计线程
            if self.config.enable_performance_monitor:
                self._stats_thread = threading.Thread(
                    target=self._run_stats_loop, name="RemoteScreenStats", daemon=True
                )
                self._stats_thread.start()

    def stop(self):
        """停止远程屏幕服务"""
        with self._lock:
            if not self.running:
                return

            self.logger.info("停止远程屏幕服务")
            self.running = False
            self._stop_event.set()

            # 停止编码工作池
            for worker in self._encode_workers:
                worker.stop()
            self._encode_workers.clear()

            # 等待线程结束
            if self._capture_thread and self._capture_thread.is_alive():
                self._capture_thread.join(timeout=5)
            if self._stats_thread and self._stats_thread.is_alive():
                self._stats_thread.join(timeout=3)

            # 清理资源
            self._cleanup_resources()

            self.logger.info("远程屏幕服务已停止")

    def _cleanup_resources(self):
        """清理资源"""
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)
                time.sleep(0.5)

            self._frame_buffer.clear()
            if self._last_frame is not None:
                self._last_frame = None
            if self._last_motion_frame is not None:
                self._last_motion_frame = None
            self._active_regions.clear()
            self._excluded_regions.clear()

            gc.collect()

        except Exception as e:
            self.logger.error(f"资源清理异常: {e}")

    def update_excluded_windows(
        self, excluded_windows: List[str], excluded_processes: List[str]
    ):
        """更新排除窗口列表"""
        with self._lock:
            self.config.excluded_windows = excluded_windows
            self.config.excluded_processes = excluded_processes

            if self.config.enable_window_exclusion:
                self._window_exclusion_manager.update_exclusions(
                    excluded_windows, excluded_processes
                )
                self.logger.info(
                    f"排除窗口已更新: windows={len(excluded_windows)}, processes={len(excluded_processes)}"
                )

    def set_window_exclusion_enabled(self, enabled: bool):
        """启用/禁用窗口排除"""
        with self._lock:
            self.config.enable_window_exclusion = enabled
            if enabled:
                self._window_exclusion_manager.update_exclusions(
                    self.config.excluded_windows, self.config.excluded_processes
                )
            self.logger.info(f"窗口排除: {'启用' if enabled else '禁用'}")

    def get_excluded_windows(self) -> Tuple[List[str], List[str]]:
        """获取排除窗口列表"""
        with self._lock:
            return (
                self.config.excluded_windows.copy(),
                self.config.excluded_processes.copy(),
            )

    def get_remote_windows(self) -> List[Dict[str, Any]]:
        """获取远程窗口列表（用于前端显示）"""
        if not self.config.enable_window_exclusion:
            return []

        try:
            windows = []
            visible_windows = self._window_exclusion_manager._get_visible_windows()

            for window in visible_windows:
                windows.append(
                    {
                        "hwnd": window.hwnd,
                        "title": window.title,
                        "process_name": window.process_name,
                        "rect": window.rect,
                        "is_excluded": self._is_window_excluded(window),
                    }
                )

            return windows

        except Exception as e:
            self.logger.error(f"获取窗口列表失败: {e}")
            return []

    def _is_window_excluded(self, window: WindowInfo) -> bool:
        """判断窗口是否被排除"""
        for excluded in self.config.excluded_windows:
            if excluded.lower() in window.title.lower():
                return True
        for excluded in self.config.excluded_processes:
            if excluded.lower() in window.process_name.lower():
                return True
        return False

    def _apply_window_exclusion(self, frame: np.ndarray) -> np.ndarray:
        """应用窗口排除（涂抹排除区域）"""
        if not self.config.enable_window_exclusion:
            return frame

        try:
            exclusion_start = time.time()

            # 获取排除区域
            excluded_regions = self._window_exclusion_manager.get_excluded_regions()
            self._excluded_regions = excluded_regions

            if not excluded_regions:
                return frame

            # 创建副本
            result = frame.copy()

            # 对排除区域进行模糊处理
            for x, y, w, h in excluded_regions:
                # 确保区域在帧范围内
                x = max(0, x)
                y = max(0, y)
                w = min(w, result.shape[1] - x)
                h = min(h, result.shape[0] - y)

                if w > 0 and h > 0:
                    # 提取区域
                    region = result[y : y + h, x : x + w]

                    # 应用高斯模糊
                    if CV2_AVAILABLE and region.size > 0:
                        blurred = cv2.GaussianBlur(region, (31, 31), 0)
                        result[y : y + h, x : x + w] = blurred
                    else:
                        # 如果没有OpenCV，填充黑色
                        result[y : y + h, x : x + w] = 0

            self.performance_metrics.exclusion_time_ms = (
                time.time() - exclusion_start
            ) * 1000

            if excluded_regions:
                self.logger.debug(f"排除了 {len(excluded_regions)} 个窗口区域")

            return result

        except Exception as e:
            self.logger.error(f"窗口排除失败: {e}")
            return frame

    def _run_capture_loop(self):
        """采集主循环"""
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            loop.run_until_complete(self._async_capture_loop())

        except Exception as e:
            self.logger.error(f"采集循环异常: {e}", exc_info=True)
        finally:
            if loop:
                loop.close()
            self._loop = None

    async def _async_capture_loop(self):
        """异步采集循环 - 生产者-消费者模式 + 自适应质量控制"""
        self.logger.info("🚀 高可靠采集循环已启动")

        # ✅ 在事件循环中创建事件
        self._frame_ready_event = asyncio.Event()

        # 状态追踪
        last_frame_time = 0.0
        last_stats_time = time.time()
        frames_captured = 0
        frames_sent_actual = 0
        last_viewer_count = 0
        consecutive_errors = 0

        # ✅ 重置计数器
        self._frames_dropped = 0

        async def sender_worker():
            """消费者协程：专注于高负载编码与网络 IO"""
            nonlocal frames_sent_actual  # ✅ 添加 nonlocal 声明
            while self.running and not self._stop_event.is_set():
                try:
                    # 1. 等待采集触发
                    try:
                        await asyncio.wait_for(
                            self._frame_ready_event.wait(), timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        continue

                    self._frame_ready_event.clear()

                    if self._latest_frame is None:
                        continue

                    # ✅ 2. 拥塞检测：如果上一帧仍在处理，丢弃当前帧以降低延迟
                    if self._frame_processing:
                        self._frames_dropped += 1
                        self._latest_frame = None
                        continue

                    # 3. 准备处理
                    current_frame = self._latest_frame
                    self._latest_frame = None
                    self._frame_processing = True

                    try:
                        send_start = time.time()
                        await self._process_frame(current_frame)
                        frames_sent_actual += 1

                        # 性能预警
                        process_time = (time.time() - send_start) * 1000
                        if process_time > 150:
                            self.logger.debug(
                                f"🐢 单帧处理耗时较长: {process_time:.1f}ms"
                            )

                    except Exception as e:
                        self.logger.error(f"❌ 帧发送流程异常: {e}")
                    finally:
                        self._frame_processing = False

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"❌ Sender Worker 核心故障: {e}")
                    await asyncio.sleep(0.1)

        # 启动后台发送任务
        sending_task = asyncio.create_task(sender_worker())

        try:
            while self.running and not self._stop_event.is_set():
                # --- A. 基础状态检查 ---
                if not await self._ensure_connection():
                    await asyncio.sleep(self.config.reconnect_delay)
                    continue

                # --- B. 观众状态联动 ---
                viewer_count = self.viewer_count
                if last_viewer_count != viewer_count:
                    if viewer_count > 0 and last_viewer_count == 0:
                        self._last_frame = None
                        self.logger.info(f"🎬 观众接入 ({viewer_count}人)，激活实时流")
                    elif viewer_count == 0 and last_viewer_count > 0:
                        self.logger.info(f"⏸️ 无观众，进入低能耗模式")
                        self._latest_frame = None
                        if self._frame_ready_event:
                            self._frame_ready_event.clear()
                    last_viewer_count = viewer_count

                if viewer_count == 0:
                    await asyncio.sleep(0.5)
                    continue

                # --- C. 精确采集节奏控制 ---
                now = time.time()
                target_interval = 1.0 / max(self.current_fps, 1)

                if last_frame_time > 0:
                    time_since_last = now - last_frame_time
                    if time_since_last < target_interval:
                        wait_time = min(target_interval - time_since_last, 0.05)
                        await asyncio.sleep(wait_time)
                        continue

                # --- D. 屏幕采集 ---
                capture_start = time.time()
                frame = await self._capture_screen()

                if frame is None:
                    consecutive_errors += 1
                    await asyncio.sleep(min(2 ** min(consecutive_errors, 3), 5))
                    continue

                consecutive_errors = 0
                frames_captured += 1
                self.performance_metrics.capture_time_ms = (
                    time.time() - capture_start
                ) * 1000

                # --- E. 交付给消费者 ---
                if self.config.enable_window_exclusion:
                    frame = self._apply_window_exclusion(frame)

                self._latest_frame = frame
                if self._frame_ready_event:
                    self._frame_ready_event.set()
                last_frame_time = time.time()

                # --- F. 自适应统计与自愈逻辑 ---
                if now - last_stats_time >= 5.0:
                    avg_capture_fps = frames_captured / 5.0
                    avg_send_fps = frames_sent_actual / 5.0
                    drop_rate = (self._frames_dropped / max(frames_captured, 1)) * 100

                    self.logger.info(
                        f"📊 5s统计: 采集={avg_capture_fps:.1f}fps, "
                        f"发送={avg_send_fps:.1f}fps, 丢弃率={drop_rate:.1f}%"
                    )

                    if drop_rate > 20 and self.current_quality > 30:
                        self.current_quality -= 10
                        self.logger.warning(
                            f"📉 负载过高，自动调低质量至: {self.current_quality}"
                        )

                    # 重置计数器
                    frames_captured = 0
                    frames_sent_actual = 0
                    self._frames_dropped = 0
                    last_stats_time = now

        finally:
            self.logger.info("⚙️ 正在安全关闭采集流程...")
            if sending_task and not sending_task.done():
                sending_task.cancel()
                try:
                    await asyncio.wait_for(sending_task, timeout=2.0)
                except:
                    pass
            self.logger.info("✅ 采集流程已彻底关闭")

    async def _ensure_connection(self) -> bool:
        """确保连接状态"""
        # 减少日志频率
        if not hasattr(self, "_last_ensure_log"):
            self._last_ensure_log = 0

        now = time.time()
        if now - self._last_ensure_log > 10:  # 每10秒打印一次
            self.logger.info(
                f"🔌 _ensure_connection: state={self.state}, ws={self.ws is not None}"
            )
            self._last_ensure_log = now

        if self.state == ConnectionState.CONNECTED and self.ws:
            return True

        if self.state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING):
            return False

        return await self._connect()

    async def _connect(self) -> bool:
        """建立WebSocket连接"""
        async with self._ws_lock:
            if self.state == ConnectionState.CONNECTED:
                return True

            self.state = ConnectionState.CONNECTING

            try:
                if not self.config.client_id:
                    self.logger.error("client_id 不存在")
                    self.state = ConnectionState.DISCONNECTED
                    return False

                # 构建WebSocket URL
                base_url = self.config.server_url.replace("http://", "ws://").replace(
                    "https://", "wss://"
                )
                ws_url = f"{base_url}/api/remote/ws/client/{self.config.client_id}"

                self.logger.info(f"连接远程屏幕服务: {ws_url}")

                # 建立连接
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        ping_interval=self.config.ws_ping_interval,
                        ping_timeout=self.config.ws_ping_timeout,
                        max_size=10 * 1024 * 1024,
                        close_timeout=5,
                    ),
                    timeout=self.config.connection_timeout,
                )

                self.state = ConnectionState.CONNECTED
                self.reconnect_attempts = 0
                self.network_stats.reconnect_count += 1

                self.logger.info("WebSocket连接成功")

                # 初始化消息队列
                self._message_queue = asyncio.Queue(maxsize=50)

                # 启动消息处理任务
                self._tasks.add(asyncio.create_task(self._message_sender()))
                self._tasks.add(asyncio.create_task(self._message_receiver()))
                self._tasks.add(asyncio.create_task(self._heartbeat_sender()))
                self._tasks.add(asyncio.create_task(self._network_monitor()))

                # 发送客户端信息
                await self._send_client_info()

                return True

            except asyncio.TimeoutError:
                self.logger.error("连接超时")
            except websockets.exceptions.InvalidStatusCode as e:
                if e.status_code == 403:
                    self.logger.error(
                        f"连接被拒绝: 客户端ID无效 {self.config.client_id}"
                    )
                elif e.status_code == 404:
                    self.logger.error("连接被拒绝: 远程屏幕服务不存在")
                else:
                    self.logger.error(f"连接失败: HTTP {e.status_code}")
            except Exception as e:
                self.logger.error(f"连接异常: {e}")

            self.state = ConnectionState.DISCONNECTED
            return False

    async def _disconnect(self):
        """断开连接"""
        self.state = ConnectionState.CLOSING

        # 取消所有任务
        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # 关闭WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None

        self.state = ConnectionState.DISCONNECTED
        self.viewer_count = 0
        self.session_id = None

        if self._message_queue:
            try:
                await self._message_queue.put(None)
            except:
                pass
        self._message_queue = None

    async def _message_sender(self):
        """消息发送器 - 支持二进制"""
        while (
            self.state == ConnectionState.CONNECTED and self._message_queue is not None
        ):
            try:
                message = await self._message_queue.get()
                if message is None:
                    break

                if self.ws:
                    if isinstance(message, bytes):
                        # ✅ 发送二进制
                        await self.ws.send(message)
                    else:
                        # 发送文本
                        await self.ws.send(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"消息发送失败: {e}")
                await asyncio.sleep(0.1)

    async def _message_receiver(self):
        """消息接收器"""
        self.logger.info("📡 消息接收循环已启动")
        message_count = 0
        while self.state == ConnectionState.CONNECTED and self.ws:
            try:
                message = await self.ws.recv()
                await self._handle_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                self.logger.warning(f"WebSocket连接关闭: {e.code} - {e.reason}")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"消息接收异常: {e}")
                await asyncio.sleep(0.1)

        # 连接断开，触发重连
        if self.running and self.state == ConnectionState.CONNECTED:
            self.state = ConnectionState.DISCONNECTED
            await self._reconnect()

    async def _heartbeat_sender(self):
        """心跳发送器"""
        heartbeat_count = 0
        while self.state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(30)
                heartbeat_count += 1

                heartbeat = {
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "client_id": self.config.client_id,
                    "viewers": self.viewer_count,
                    "stats": self._get_stats_dict(),
                    "sequence": heartbeat_count,
                    "excluded_windows_count": (
                        len(self._excluded_regions)
                        if self.config.enable_window_exclusion
                        else 0
                    ),
                }

                if self._message_queue:
                    await self._message_queue.put(json.dumps(heartbeat))

                self.logger.debug(f"心跳已发送 #{heartbeat_count}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.debug(f"心跳发送失败: {e}")

    async def _network_monitor(self):
        """网络监控器 - 增强版（支持带宽估算和高级参数调整）"""
        # ✅ 记录上次更新的字节数
        last_bytes = 0
        last_time = time.time()

        while self.state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self.config.network_check_interval)

                # 发送ping
                start = time.time()
                ping_msg = {
                    "type": "ping",
                    "timestamp": start,
                    "client_id": self.config.client_id,
                }

                if self.ws:
                    await self.ws.send(json.dumps(ping_msg))

                    try:
                        response = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                        data = json.loads(response)

                        if data.get("type") == "pong":
                            latency = (time.time() - start) * 1000
                            self._update_network_stats(latency)

                    except asyncio.TimeoutError:
                        self.logger.debug("Ping超时")
                        self._update_network_stats(1000)

                # ✅ 使用高级参数调整（基于带宽和延迟）
                await self._adjust_parameters_advanced()

                # ✅ 更新带宽估算器（计算增量）
                current_bytes = self.network_stats.bytes_sent
                current_time = time.time()

                if hasattr(self, "bandwidth_estimator") and current_bytes > last_bytes:
                    # 计算增量并更新
                    bytes_delta = current_bytes - last_bytes
                    self.bandwidth_estimator.update(bytes_delta, current_time)

                    # 可选：记录带宽信息（调试用）
                    if self.config.enable_detailed_logging:
                        bw_mbps = self.bandwidth_estimator.get_bandwidth_mbps()
                        self.logger.debug(
                            f"📊 估算带宽: {bw_mbps:.1f} Mbps (增量={bytes_delta/1024:.1f}KB)"
                        )

                last_bytes = current_bytes
                last_time = current_time

                # 定期更新窗口排除缓存
                if self.config.enable_window_exclusion:
                    self._window_exclusion_manager.clear_cache()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.debug(f"网络监控异常: {e}")

    async def _reconnect(self):
        """重连逻辑"""
        if self.reconnect_attempts >= self.config.max_reconnect_attempts:
            self.logger.error("达到最大重连次数，停止服务")
            self.running = False
            return

        self.state = ConnectionState.RECONNECTING
        self.reconnect_attempts += 1

        delay = self.config.reconnect_delay * self.reconnect_attempts
        self.logger.info(
            f"等待 {delay:.1f}秒 后重连 (尝试 {self.reconnect_attempts}/{self.config.max_reconnect_attempts})"
        )

        await asyncio.sleep(delay)

        if self.running:
            await self._connect()

    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            # 记录原始消息前200字符用于调试
            self.logger.info(f"📨 处理消息: {message[:200]}")
            data = json.loads(message)
            msg_type = data.get("type")
            self.logger.info(f"📩 消息类型: {msg_type}")

            # --- 1. 观众数量同步逻辑 (核心修复点) ---
            # 只要消息里带了 viewers 字段（无论什么消息类型），都尝试同步，确保状态实时
            if "viewers" in data:
                old_count = self.viewer_count
                try:
                    self.viewer_count = int(data.get("viewers", 0))
                except (ValueError, TypeError):
                    self.viewer_count = 0

                if old_count != self.viewer_count:
                    self.logger.info(
                        f"👥 观众数量同步: {old_count} -> {self.viewer_count}"
                    )

                    if self.viewer_count > 0 and old_count == 0:
                        self.logger.info("🎬 有观众连接，开始采集屏幕画面")
                        # ✅ 关键修复：重置参考帧，确保下一帧是全量关键帧
                        self._last_frame = None
                        self._last_motion_frame = None
                        self.logger.info("📸 已重置参考帧，下一帧将发送完整画面")
                    elif self.viewer_count == 0 and old_count > 0:
                        self.logger.info("⏸️ 所有观众离开，停止采集屏幕画面")
                        self._frame_buffer.clear()  # 停止采集时清空缓冲
                        # ✅ 新增：清空待处理帧
                        if hasattr(self, "_latest_frame"):
                            self._latest_frame = None
                        if hasattr(self, "_frame_ready_event"):
                            self._frame_ready_event.clear()

            # --- 2. 各消息类型具体分支 ---
            if msg_type == "viewer_update":
                # 观众更新已经在上面通用逻辑处理了，此处保留分支以防未来扩展
                pass

            elif msg_type == "command":
                await self._handle_command(data)

            elif msg_type == "config":
                self._handle_config_update(data.get("config", {}))

            elif msg_type == "connected":
                self.session_id = data.get("session_id")
                # 会话连接成功时，确保初始化观众数
                if "viewers" in data:
                    old_count = self.viewer_count
                    self.viewer_count = int(data.get("viewers", 0))
                    self.logger.info(
                        f"会话建立成功: session_id={self.session_id}, 观众数={self.viewer_count}"
                    )
                    # ✅ 如果连接时就有观众，重置参考帧
                    if self.viewer_count > 0 and old_count == 0:
                        self._last_frame = None
                        self._last_motion_frame = None
                        self.logger.info("📸 会话建立时有观众，重置参考帧")

            # ✅ 新增：处理停止查看消息
            elif msg_type == "stop_view":
                self.logger.info("📴 收到停止查看消息，立即停止采集")
                self.viewer_count = 0
                self._frame_buffer.clear()

                # 重置帧状态
                self._last_frame = None
                self._last_motion_frame = None

                # ✅ 清空生产者-消费者变量（现在是实例属性）
                self._latest_frame = None
                if self._frame_ready_event:
                    self._frame_ready_event.clear()
                self._frame_processing = False

                # 清空待发送消息队列
                if self._message_queue:
                    try:
                        while not self._message_queue.empty():
                            self._message_queue.get_nowait()
                    except Exception:
                        pass

            elif msg_type == "close":
                self.logger.info("📴 收到前端关闭消息，立即停止采集")
                self.viewer_count = 0
                self._frame_buffer.clear()
                # 重置帧状态，确保下次开启时发送完整帧
                if hasattr(self, "_last_frame"):
                    self._last_frame = None
                if hasattr(self, "_last_motion_frame"):
                    self._last_motion_frame = None
                # 清空待发送消息队列
                if self._message_queue:
                    try:
                        while not self._message_queue.empty():
                            self._message_queue.get_nowait()
                    except Exception:
                        pass

            elif msg_type == "admin_left":
                if "viewers" not in data:
                    old_count = self.viewer_count
                    self.viewer_count = max(0, self.viewer_count - 1)
                    self.logger.info(
                        f"👋 管理员离开，本地计算观众数: {old_count} -> {self.viewer_count}"
                    )
                    if self.viewer_count == 0:
                        self.logger.info("⏸️ 所有观众离开，停止采集")
                        self._frame_buffer.clear()
                        # ✅ 清空待处理帧
                        if hasattr(self, "_latest_frame"):
                            self._latest_frame = None
                        if hasattr(self, "_frame_ready_event"):
                            self._frame_ready_event.clear()

            elif msg_type == "pong":
                # 标准心跳响应，不做特殊处理
                pass

            elif msg_type == "heartbeat_ack":
                # 更新网络延迟统计
                if "timestamp" in data:
                    latency = (time.time() - data["timestamp"]) * 1000
                    self._update_network_stats(latency)

            elif msg_type == "get_remote_windows":
                # 处理获取窗口列表请求
                windows = self.get_remote_windows()
                response = {
                    "type": "remote_windows",
                    "windows": windows,
                    "timestamp": time.time(),
                }
                if self._message_queue:
                    await self._message_queue.put(json.dumps(response))

            elif msg_type == "update_excluded_windows":
                # 处理排除窗口配置变更
                excluded_windows = data.get("excluded_windows", [])
                excluded_processes = data.get("excluded_processes", [])
                self.update_excluded_windows(excluded_windows, excluded_processes)

            elif msg_type == "set_window_exclusion":
                # 切换窗口排除功能的启用状态
                enabled = data.get("enabled", False)
                self.set_window_exclusion_enabled(enabled)

            elif msg_type == "error":
                error_msg = data.get("message", "未知错误")
                self.logger.error(f"服务器反馈错误: {error_msg}")
                if hasattr(self, "network_stats"):
                    self.network_stats.last_error = error_msg
                    self.network_stats.error_count += 1

            else:
                self.logger.debug(f"未处理的消息类型: {msg_type}")

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {e}, 消息: {message[:200]}")
        except Exception as e:
            self.logger.error(f"消息处理异常: {e}", exc_info=True)

    async def _handle_command(self, command: dict):
        """处理管理员命令"""
        cmd = command.get("command")
        params = command.get("params", {})

        if cmd == "quality":
            new_quality = params.get("quality", self.current_quality)
            self.current_quality = max(
                self.config.min_quality, min(self.config.max_quality, new_quality)
            )
            self.logger.info(f"质量调整: {self.current_quality}")

        elif cmd == "fps":
            new_fps = params.get("fps", self.current_fps)
            self.current_fps = max(
                self.config.min_fps, min(self.config.max_fps, new_fps)
            )
            self.logger.info(f"帧率调整: {self.current_fps}")

        elif cmd == "width":
            new_width = params.get("width", self.current_width)
            self.current_width = max(
                self.config.min_width, min(self.config.max_width, new_width)
            )
            self.logger.info(f"宽度调整: {self.current_width}")

        elif cmd == "fullscreen":
            frame = await self._capture_screen()
            if frame is not None:
                await self._process_frame(frame, force_full=True)

        elif cmd == "diff_enable":
            self.config.enable_diff_frame = params.get("enable", True)
            self.logger.info(
                f"差异帧传输: {'启用' if self.config.enable_diff_frame else '禁用'}"
            )

        elif cmd == "region_enable":
            self.config.enable_region_detect = params.get("enable", True)
            self.logger.info(
                f"区域检测: {'启用' if self.config.enable_region_detect else '禁用'}"
            )

        elif cmd == "qr_enable":
            self.config.enable_qr_detect = params.get("enable", False)
            self.logger.info(
                f"二维码检测: {'启用' if self.config.enable_qr_detect else '禁用'}"
            )

        elif cmd == "window_exclusion_enable":
            enabled = params.get("enable", False)
            self.set_window_exclusion_enabled(enabled)

        elif cmd == "reset":
            self.current_quality = self.config.initial_quality
            self.current_fps = self.config.initial_fps
            self.current_width = self.config.max_width
            self.logger.info("参数已重置")

    def _handle_config_update(self, config: dict):
        """处理配置更新"""
        with self._lock:
            if "fps" in config:
                self.current_fps = max(
                    self.config.min_fps, min(self.config.max_fps, config["fps"])
                )
            if "quality" in config:
                self.current_quality = max(
                    self.config.min_quality,
                    min(self.config.max_quality, config["quality"]),
                )
            if "width" in config:
                self.current_width = max(
                    self.config.min_width, min(self.config.max_width, config["width"])
                )
            if "enable_diff" in config:
                self.config.enable_diff_frame = config["enable_diff"]
            if "enable_region" in config:
                self.config.enable_region_detect = config["enable_region"]
            if "enable_window_exclusion" in config:
                self.set_window_exclusion_enabled(config["enable_window_exclusion"])
            if "excluded_windows" in config:
                self.update_excluded_windows(
                    config.get("excluded_windows", []),
                    config.get("excluded_processes", []),
                )

    async def _send_client_info(self):
        """发送客户端信息"""
        info = {
            "type": "client_info",
            "timestamp": time.time(),
            "client_id": self.config.client_id,
            "employee_id": self.config.employee_id,
            "capabilities": {
                "diff_frame": self.config.enable_diff_frame,
                "region_detect": self.config.enable_region_detect,
                "h264": self.config.enable_h264,
                "qr_detect": self.config.enable_qr_detect,
                "window_exclusion": self.config.enable_window_exclusion,
                "max_fps": self.config.max_fps,
                "max_quality": self.config.max_quality,
                "max_width": self.config.max_width,
                "min_fps": self.config.min_fps,
                "min_quality": self.config.min_quality,
                "min_width": self.config.min_width,
            },
            "system": {
                "python_version": sys.version,
                "platform": sys.platform,
                "cv2_available": CV2_AVAILABLE,
                "mss_available": MSS_AVAILABLE,
                "window_exclusion_available": WINDOWS_AVAILABLE or LINUX_AVAILABLE,
            },
            "excluded_windows": self.config.excluded_windows,
            "excluded_processes": self.config.excluded_processes,
        }

        if self._message_queue:
            await self._message_queue.put(json.dumps(info))
            self.logger.info("客户端信息已发送")

    async def _process_frame(self, frame: np.ndarray, force_full: bool = False):
        """低延迟优化版：静帧降频 + 智能帧类型选择 + 关键帧管理"""

        if self.state != ConnectionState.CONNECTED:
            return

        if self.viewer_count == 0:
            return

        now = time.time()

        # ✅ 初始化发送时间控制
        if not hasattr(self, "_last_send_time"):
            self._last_send_time = 0
        if not hasattr(self, "_last_idle_time"):
            self._last_idle_time = 0
        if not hasattr(self, "_keyframe_manager"):
            # 关键帧管理器
            self._keyframe_manager = {
                "last_keyframe_time": 0,
                "keyframe_interval": 5.0,  # 每5秒强制发一次完整帧
                "motion_buffer": [],  # 运动历史缓冲
                "max_buffer_size": 10,
            }

        frame_type = FrameType.FULL
        should_send = True

        # 强制发送完整帧
        if force_full:
            self._last_frame = frame.copy()
            await self._encode_and_send(frame, FrameType.FULL)
            self._last_send_time = now
            self._keyframe_manager["last_keyframe_time"] = now
            self._keyframe_manager["motion_buffer"].clear()
            return

        # 差异检测（仅当启用且存在参考帧）
        if self.config.enable_diff_frame and self._last_frame is not None:
            try:
                diff_ratio = self._calculate_diff_ratio(frame, self._last_frame)

                # ✅ 关键帧检测
                need_keyframe = False

                # 1. 定时刷新（防止累积误差）
                if (
                    now - self._keyframe_manager["last_keyframe_time"]
                    > self._keyframe_manager["keyframe_interval"]
                ):
                    need_keyframe = True

                # 2. 剧烈变化检测
                if diff_ratio > 0.8:
                    need_keyframe = True

                # 3. 累积运动检测
                motion_buffer = self._keyframe_manager["motion_buffer"]
                motion_buffer.append(diff_ratio)
                if len(motion_buffer) > self._keyframe_manager["max_buffer_size"]:
                    motion_buffer.pop(0)
                if len(motion_buffer) >= 5:
                    avg_motion = sum(motion_buffer[-5:]) / 5
                    if avg_motion > 0.3:
                        need_keyframe = True

                # 发送关键帧
                if need_keyframe:
                    frame_type = FrameType.FULL
                    self._keyframe_manager["last_keyframe_time"] = now
                    self._keyframe_manager["motion_buffer"].clear()
                    self.logger.debug(
                        f"📸 关键帧发送 (diff={diff_ratio:.2%}, 原因: {'定时刷新' if now - self._keyframe_manager['last_keyframe_time'] > 5 else '变化检测'})"
                    )

                # ✅ 优化：根据变化程度决定帧类型和发送策略
                elif diff_ratio < 0.01:  # 画面几乎静止（<1%变化）
                    # 静帧模式：降频发送，保持连接活跃
                    # 每0.5秒发一帧静帧（保持连接）
                    if now - self._last_idle_time < 0.5:
                        should_send = False
                        if not hasattr(self, "_idle_frame_count"):
                            self._idle_frame_count = 0
                        self._idle_frame_count += 1
                    else:
                        self._last_idle_time = now
                        self._idle_frame_count = 0
                        frame_type = FrameType.FULL
                        if self.config.enable_detailed_logging:
                            self.logger.debug(
                                f"🖼️ 静帧保持帧发送 (diff={diff_ratio:.4f})"
                            )

                elif diff_ratio < 0.3:  # 轻微变化（<30%）
                    frame_type = FrameType.DIFF
                    if self.config.enable_detailed_logging:
                        self.logger.debug(f"🔄 差异帧发送 (diff={diff_ratio:.2%})")

                elif diff_ratio < 0.8:  # 中度变化（30%-80%）
                    if self.config.enable_region_detect:
                        frame_type = FrameType.REGION
                        if self.config.enable_detailed_logging:
                            self.logger.debug(f"📦 区域帧发送 (diff={diff_ratio:.2%})")
                    else:
                        frame_type = FrameType.FULL
                else:  # 剧烈变化（>80%）
                    frame_type = FrameType.FULL
                    if self.config.enable_detailed_logging:
                        self.logger.debug(f"📸 完整帧发送 (diff={diff_ratio:.2%})")

            except Exception as e:
                self.logger.error(f"⚠️ 差异计算失败: {e}")
                frame_type = FrameType.FULL
        else:
            # 没有参考帧，发送完整帧
            frame_type = FrameType.FULL
            # 重置关键帧计时器
            self._keyframe_manager["last_keyframe_time"] = now

        # ✅ 更新参考帧（无论是否发送，都要更新）
        self._last_frame = frame.copy()

        # 发送帧
        if should_send:
            await self._encode_and_send(frame, frame_type)
            self._last_send_time = now

            # 记录帧类型统计
            if not hasattr(self, "_frame_type_stats"):
                self._frame_type_stats = {"full": 0, "diff": 0, "region": 0, "idle": 0}

            frame_type_key = frame_type.value
            self._frame_type_stats[frame_type_key] = (
                self._frame_type_stats.get(frame_type_key, 0) + 1
            )

            # 每100帧打印一次统计
            total_frames = sum(self._frame_type_stats.values())
            if total_frames % 100 == 0:
                self.logger.info(
                    f"📊 帧类型统计: FULL={self._frame_type_stats.get('full_frame', 0)}, "
                    f"DIFF={self._frame_type_stats.get('diff_frame', 0)}, "
                    f"REGION={self._frame_type_stats.get('region_frame', 0)}, "
                    f"静帧跳过={self._frame_type_stats.get('idle', 0)}"
                )
        else:
            # 记录跳过的静帧
            if not hasattr(self, "_frame_type_stats"):
                self._frame_type_stats = {}
            self._frame_type_stats["idle"] = self._frame_type_stats.get("idle", 0) + 1

    def _calculate_diff_ratio(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """计算差异比例"""
        if not CV2_AVAILABLE:
            return 1.0

        try:
            if frame1.shape != frame2.shape:
                return 1.0

            diff = cv2.absdiff(frame1, frame2)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

            changed_pixels = cv2.countNonZero(thresh)
            total_pixels = frame1.shape[0] * frame1.shape[1]

            return changed_pixels / total_pixels if total_pixels > 0 else 1.0

        except Exception as e:
            self.logger.debug(f"差异计算失败: {e}")
            return 1.0

    async def _encode_and_send(self, frame: np.ndarray, frame_type: FrameType):
        """编码并发送帧 - 包含智能频率控制"""
        try:
            now = time.time()

            # ✅ 1. 频率检测（放在最前面，节省 CPU）
            if hasattr(self, "_last_send_time"):
                time_since_last_send = now - self._last_send_time
                # 留出 10% 的余量，防止因为微小的计时误差导致掉帧
                min_interval = (1.0 / max(self.current_fps, 1)) * 0.9
                if time_since_last_send < min_interval:
                    # 频率太高，直接丢弃该帧以保护带宽
                    return

            # ✅ 2. 异步编码
            encode_start = time.time()
            encoded_data = await self._encode_frame_async(frame, frame_type)

            encode_time = (time.time() - encode_start) * 1000
            self.performance_metrics.encode_time_ms = encode_time

            # 维护编码时间历史（建议限制长度，防止内存泄漏）
            self.network_stats.encode_times.append(encode_time)
            if len(self.network_stats.encode_times) > 100:
                self.network_stats.encode_times.pop(0)

            # ✅ 3. 发送数据
            if encoded_data:
                await self._send_frame(encoded_data, frame_type)

                # 更新统计
                self.network_stats.frames_sent += 1
                self.network_stats.bytes_sent += len(encoded_data)

                # 计算平均大小
                if self.network_stats.frames_sent > 0:
                    self.network_stats.avg_frame_size = (
                        self.network_stats.bytes_sent / self.network_stats.frames_sent
                    )

                # ✅ 更新最后成功发送时间
                self._last_send_time = time.time()

                # 定期打印进度 (debug 级别)
                if self.network_stats.frames_sent % 30 == 0:
                    self.logger.debug(
                        f"🚀 发送统计: 已发送={self.network_stats.frames_sent}帧, "
                        f"流量={self.network_stats.bytes_sent / 1024 / 1024:.2f}MB, "
                        f"编码={encode_time:.1f}ms"
                    )

        except Exception as e:
            self.logger.error(f"❌ 编码或发送过程发生异常: {e}", exc_info=True)
            self.network_stats.dropped_frames += 1

    async def _encode_frame_async(
        self, frame: np.ndarray, frame_type: FrameType
    ) -> Optional[bytes]:
        """异步编码帧"""
        try:
            if frame_type == FrameType.FULL:
                return await self._encode_full_frame(frame, self._get_target_quality())
            elif frame_type == FrameType.DIFF:
                return await self._encode_diff_frame(frame, self._get_target_quality())
            elif frame_type == FrameType.REGION:
                return await self._encode_region_frame(
                    frame, self._get_target_quality()
                )
            else:
                return await self._encode_full_frame(frame, self._get_target_quality())

        except Exception as e:
            self.logger.error(f"编码失败: {e}")
            return None

    async def _encode_full_frame(
        self, frame: np.ndarray, quality: int
    ) -> Optional[bytes]:
        try:
            self.logger.info(f"🎨 开始编码帧: shape={frame.shape}, quality={quality}")

            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)

            buffer = io.BytesIO()
            pil_img.save(buffer, format="JPEG", quality=quality, optimize=True)
            jpeg_data = buffer.getvalue()

            self.logger.info(f"📸 JPEG编码完成: {len(jpeg_data)} bytes")

            # 检查 JPEG 有效性
            if len(jpeg_data) < 100:
                self.logger.error(f"❌ JPEG数据过小: {len(jpeg_data)} bytes")
                return None

            # ✅ 直接返回 JPEG 数据，不再压缩
            # 因为 WebSocket 二进制传输已经足够高效，不需要额外的 zlib 压缩
            return jpeg_data

        except Exception as e:
            self.logger.error(f"完整帧编码失败: {e}", exc_info=True)
            return None

    async def _encode_diff_frame(
        self, frame: np.ndarray, quality: int
    ) -> Optional[bytes]:
        """编码差异帧"""
        if self._last_frame is None:
            return None

        try:
            diff = cv2.absdiff(frame, self._last_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=2)

            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return None

            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w * h > self.config.diff_area_threshold:
                    regions.append((x, y, w, h))

            if not regions:
                return None

            merged_regions = self._merge_regions(regions)

            region_data = []
            for x, y, w, h in merged_regions:
                region = frame[y : y + h, x : x + w]
                img_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
                pil_region = Image.fromarray(img_rgb)

                buffer = io.BytesIO()
                pil_region.save(buffer, format="JPEG", quality=quality, optimize=True)

                region_data.append(
                    {
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
                    }
                )

            diff_package = {
                "type": "diff_frame",
                "regions": region_data,
                "base_quality": quality,
                "timestamp": time.time(),
                "full_width": frame.shape[1],
                "full_height": frame.shape[0],
            }

            diff_json = json.dumps(diff_package)
            return zlib.compress(diff_json.encode("utf-8"), level=6)

        except Exception as e:
            self.logger.error(f"差异帧编码失败: {e}")
            return None

    async def _encode_region_frame(
        self, frame: np.ndarray, quality: int
    ) -> Optional[bytes]:
        """编码区域帧"""
        if self._last_motion_frame is None:
            self._last_motion_frame = frame.copy()
            return None

        try:
            diff = cv2.absdiff(frame, self._last_motion_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, 20, 255, cv2.THRESH_BINARY)

            kernel = np.ones((10, 10), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=3)

            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w * h > self.config.region_area_threshold:
                    regions.append((x, y, w, h))

            if not regions:
                return None

            merged_regions = self._merge_regions(regions)
            self._active_regions = merged_regions

            bg_rgb = cv2.cvtColor(self._last_motion_frame, cv2.COLOR_BGR2RGB)
            pil_bg = Image.fromarray(bg_rgb)
            bg_buffer = io.BytesIO()
            pil_bg.save(bg_buffer, format="JPEG", quality=quality // 2, optimize=True)
            bg_data = base64.b64encode(bg_buffer.getvalue()).decode("utf-8")

            region_data = []
            for x, y, w, h in merged_regions:
                region = frame[y : y + h, x : x + w]
                region_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
                pil_region = Image.fromarray(region_rgb)

                buffer = io.BytesIO()
                pil_region.save(buffer, format="JPEG", quality=quality, optimize=True)

                region_data.append(
                    {
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
                    }
                )

            region_package = {
                "type": "region_frame",
                "background": bg_data,
                "regions": region_data,
                "quality": quality,
                "timestamp": time.time(),
                "full_width": frame.shape[1],
                "full_height": frame.shape[0],
            }

            region_json = json.dumps(region_package)
            self._last_motion_frame = frame.copy()

            return zlib.compress(region_json.encode("utf-8"), level=6)

        except Exception as e:
            self.logger.error(f"区域帧编码失败: {e}")
            return None

    def _encode_full_frame_sync(
        self, frame: np.ndarray, quality: int
    ) -> Optional[bytes]:
        try:
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)

            buffer = io.BytesIO()
            pil_img.save(buffer, format="JPEG", quality=quality, optimize=True)

            # ✅ 直接返回 JPEG 数据
            return buffer.getvalue()

        except Exception as e:
            self.logger.error(f"同步完整帧编码失败: {e}")
            return None

    def _encode_diff_frame_sync(
        self, frame: np.ndarray, quality: int
    ) -> Optional[bytes]:
        """同步编码差异帧"""
        if self._last_frame is None:
            return None

        try:
            diff = cv2.absdiff(frame, self._last_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=2)

            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return None

            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w * h > self.config.diff_area_threshold:
                    regions.append((x, y, w, h))

            if not regions:
                return None

            merged_regions = self._merge_regions(regions)

            region_data = []
            for x, y, w, h in merged_regions:
                region = frame[y : y + h, x : x + w]
                img_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
                pil_region = Image.fromarray(img_rgb)

                buffer = io.BytesIO()
                pil_region.save(buffer, format="JPEG", quality=quality, optimize=True)

                region_data.append(
                    {
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
                    }
                )

            diff_package = {
                "type": "diff_frame",
                "regions": region_data,
                "base_quality": quality,
                "timestamp": time.time(),
                "full_width": frame.shape[1],
                "full_height": frame.shape[0],
            }

            diff_json = json.dumps(diff_package)
            return zlib.compress(diff_json.encode("utf-8"), level=6)

        except Exception as e:
            self.logger.error(f"同步差异帧编码失败: {e}")
            return None

    def _encode_region_frame_sync(
        self, frame: np.ndarray, quality: int
    ) -> Optional[bytes]:
        """同步编码区域帧"""
        if self._last_motion_frame is None:
            self._last_motion_frame = frame.copy()
            return None

        try:
            diff = cv2.absdiff(frame, self._last_motion_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, 20, 255, cv2.THRESH_BINARY)

            kernel = np.ones((10, 10), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=3)

            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w * h > self.config.region_area_threshold:
                    regions.append((x, y, w, h))

            if not regions:
                return None

            merged_regions = self._merge_regions(regions)
            self._active_regions = merged_regions

            bg_rgb = cv2.cvtColor(self._last_motion_frame, cv2.COLOR_BGR2RGB)
            pil_bg = Image.fromarray(bg_rgb)
            bg_buffer = io.BytesIO()
            pil_bg.save(bg_buffer, format="JPEG", quality=quality // 2, optimize=True)
            bg_data = base64.b64encode(bg_buffer.getvalue()).decode("utf-8")

            region_data = []
            for x, y, w, h in merged_regions:
                region = frame[y : y + h, x : x + w]
                region_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
                pil_region = Image.fromarray(region_rgb)

                buffer = io.BytesIO()
                pil_region.save(buffer, format="JPEG", quality=quality, optimize=True)

                region_data.append(
                    {
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
                    }
                )

            region_package = {
                "type": "region_frame",
                "background": bg_data,
                "regions": region_data,
                "quality": quality,
                "timestamp": time.time(),
                "full_width": frame.shape[1],
                "full_height": frame.shape[0],
            }

            region_json = json.dumps(region_package)
            self._last_motion_frame = frame.copy()

            return zlib.compress(region_json.encode("utf-8"), level=6)

        except Exception as e:
            self.logger.error(f"同步区域帧编码失败: {e}")
            return None

    async def _send_frame(self, encoded_data: bytes, frame_type: FrameType):
        """发送帧数据 - 二进制优化版"""

        if not self.state == ConnectionState.CONNECTED or self._message_queue is None:
            return

        # ✅ 方案1：直接发送二进制（推荐）
        try:
            # 添加简单帧头（可选）
            # 格式: [帧类型(1字节)] + [宽度(2字节)] + [高度(2字节)] + JPEG数据
            width = self.current_width
            height = int(width * 9 / 16)

            header = bytearray()
            header.append(1)  # 版本号
            header.append(self._get_frame_type_code(frame_type))
            header.extend(width.to_bytes(2, "big"))
            header.extend(height.to_bytes(2, "big"))

            binary_frame = bytes(header) + encoded_data

            # 直接放入队列（需要队列支持二进制）
            await self._message_queue.put(binary_frame)

        except Exception as e:
            # 降级到文本发送
            frame_message = {
                "type": "frame",
                "data": base64.b64encode(encoded_data).decode("utf-8"),
                "timestamp": datetime.now().isoformat(),
                "client_id": self.config.client_id,
                "compressed": True,
                "width": self.current_width,
                "height": int(self.current_width * 9 / 16),
                "frame_type": frame_type.value,
            }
            await self._message_queue.put(json.dumps(frame_message))

    def _get_frame_type_code(self, frame_type: FrameType) -> int:
        """获取帧类型编码"""
        codes = {
            FrameType.FULL: 1,
            FrameType.DIFF: 2,
            FrameType.REGION: 3,
        }
        return codes.get(frame_type, 1)

    async def _capture_screen(self) -> Optional[np.ndarray]:
        """采集屏幕"""
        try:
            if MSS_AVAILABLE:
                with mss.mss() as sct:
                    monitors = sct.monitors[1:]
                    if not monitors:
                        return None

                    if len(monitors) == 1:
                        screenshot = sct.grab(monitors[0])
                        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    else:
                        total_width = sum(m["width"] for m in monitors)
                        max_height = max(m["height"] for m in monitors)
                        merged = Image.new("RGB", (total_width, max_height))

                        x_offset = 0
                        for monitor in monitors:
                            screenshot = sct.grab(monitor)
                            img = Image.frombytes(
                                "RGB", screenshot.size, screenshot.rgb
                            )
                            merged.paste(img, (x_offset, 0))
                            x_offset += monitor["width"]

                        img_cv = cv2.cvtColor(np.array(merged), cv2.COLOR_RGB2BGR)

            elif PIL_AVAILABLE:
                pil_img = ImageGrab.grab(all_screens=True)
                img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            else:
                self.logger.error("没有可用的屏幕捕获库")
                return None

            # 缩放
            target_width = self._get_target_width()
            if img_cv.shape[1] > target_width:
                ratio = target_width / img_cv.shape[1]
                new_height = int(img_cv.shape[0] * ratio)
                img_cv = cv2.resize(
                    img_cv, (target_width, new_height), interpolation=cv2.INTER_AREA
                )

            # 二维码检测
            if self.config.enable_qr_detect and ZBAR_AVAILABLE:
                await self._detect_qr_codes(img_cv)

            return img_cv

        except Exception as e:
            self.logger.error(f"屏幕捕获失败: {e}")
            return None

    async def _detect_qr_codes(self, frame: np.ndarray):
        """检测二维码"""
        try:
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            decoded_objects = pyzbar.decode(pil_img)

            if decoded_objects:
                qr_data = []
                for obj in decoded_objects:
                    qr_data.append(
                        {
                            "data": obj.data.decode("utf-8", errors="ignore"),
                            "type": str(obj.type),
                            "rect": {
                                "x": obj.rect.left,
                                "y": obj.rect.top,
                                "width": obj.rect.width,
                                "height": obj.rect.height,
                            },
                        }
                    )

                qr_msg = {
                    "type": "qr_detected",
                    "timestamp": time.time(),
                    "qr_codes": qr_data,
                    "client_id": self.config.client_id,
                }

                if self._message_queue:
                    await self._message_queue.put(json.dumps(qr_msg))

        except Exception as e:
            self.logger.debug(f"二维码检测失败: {e}")

    def _merge_regions(self, regions: List[Tuple]) -> List[Tuple]:
        """合并重叠区域"""
        if not regions:
            return []

        regions = sorted(regions, key=lambda r: (r[0], r[1]))
        merged = []
        current = list(regions[0])

        for r in regions[1:]:
            x, y, w, h = r

            if (
                x < current[0] + current[2] + self.config.merge_distance
                and y < current[1] + current[3] + self.config.merge_distance
            ):
                new_x = min(current[0], x)
                new_y = min(current[1], y)
                new_w = max(current[0] + current[2], x + w) - new_x
                new_h = max(current[1] + current[3], y + h) - new_y
                current = [new_x, new_y, new_w, new_h]
            else:
                merged.append(tuple(current))
                current = list(r)

        merged.append(tuple(current))
        return merged

    def _update_network_stats(self, latency_ms: float):
        """更新网络统计"""
        with self._lock:
            self.network_stats.round_trip_times.append(latency_ms)

            if latency_ms < 50:
                quality = 100
            elif latency_ms < 100:
                quality = 80
            elif latency_ms < 200:
                quality = 60
            elif latency_ms < 500:
                quality = 40
            elif latency_ms < 1000:
                quality = 20
            else:
                quality = 10

            self.network_stats.network_quality = int(
                self.network_stats.network_quality * 0.7 + quality * 0.3
            )

    async def _adjust_parameters(self):
        """动态调整参数"""
        with self._lock:
            if not self.network_stats.round_trip_times:
                return

            avg_latency = sum(self.network_stats.round_trip_times[-5:]) / min(
                5, len(self.network_stats.round_trip_times)
            )

        if avg_latency > self.config.latency_threshold_high:
            new_quality = max(self.config.min_quality, self.current_quality - 5)
            new_width = max(self.config.min_width, self.current_width - 100)

            if new_quality != self.current_quality:
                self.current_quality = new_quality
                self.logger.info(f"弱网降级: 质量={new_quality}")

            if new_width != self.current_width:
                self.current_width = new_width
                self.logger.info(f"弱网降级: 宽度={new_width}")

        elif avg_latency < self.config.latency_threshold_low:
            new_quality = min(self.config.max_quality, self.current_quality + 3)
            new_width = min(self.config.max_width, self.current_width + 50)

            if new_quality != self.current_quality:
                self.current_quality = new_quality
                self.logger.info(f"网络恢复: 质量={new_quality}")

            if new_width != self.current_width:
                self.current_width = new_width
                self.logger.info(f"网络恢复: 宽度={new_width}")

    async def _adjust_parameters_advanced(self):
        """高级参数调整 - 基于带宽和延迟"""
        with self._lock:
            if not self.network_stats.round_trip_times:
                return

            # 计算网络质量指标
            rtts = list(self.network_stats.round_trip_times)
            if len(rtts) < 3:
                return

            # 延迟指标
            avg_latency = sum(rtts[-5:]) / min(5, len(rtts))
            jitter = max(rtts[-5:]) - min(rtts[-5:])

            # 带宽指标
            estimated_bw = self.bandwidth_estimator.get_bandwidth()
            bw_mbps = estimated_bw / (1024 * 1024)

            # 丢包估算（通过帧丢弃率）
            drop_rate = 0
            if self.network_stats.frames_sent > 0:
                drop_rate = (
                    self.network_stats.dropped_frames / self.network_stats.frames_sent
                )

            # 计算网络评分 (0-100)
            latency_score = max(0, min(100, 100 - avg_latency / 5))
            jitter_score = max(0, min(100, 100 - jitter / 2))
            bandwidth_score = min(100, (bw_mbps / 10) * 100)

            network_score = (
                latency_score * 0.4 + jitter_score * 0.3 + bandwidth_score * 0.3
            )

            # 根据网络评分调整参数
            if network_score > 80:  # 优秀网络
                target_quality = self.config.max_quality
                target_width = self.config.max_width
                target_fps = self.config.max_fps

            elif network_score > 60:  # 良好网络
                target_quality = min(self.config.max_quality, 85)
                target_width = min(self.config.max_width, 1280)
                target_fps = min(self.config.max_fps, 10)

            elif network_score > 40:  # 一般网络
                target_quality = 70
                target_width = 1024
                target_fps = 6

            elif network_score > 20:  # 较差网络
                target_quality = 50
                target_width = 800
                target_fps = 4

            else:  # 极差网络
                target_quality = self.config.min_quality
                target_width = self.config.min_width
                target_fps = self.config.min_fps

            # 特殊处理：高延迟时降低帧率
            if avg_latency > 500:
                target_fps = max(self.config.min_fps, 1)
            elif avg_latency > 300:
                target_fps = max(self.config.min_fps, 2)
            elif avg_latency > 150:
                target_fps = max(self.config.min_fps, 3)

            # 特殊处理：高丢包时降低质量
            if drop_rate > 0.2:
                target_quality = max(self.config.min_quality, target_quality - 20)

            # 应用新参数
            changed = False
            if target_quality != self.current_quality:
                self.current_quality = target_quality
                self.logger.info(
                    f"网络自适应: 质量={target_quality} (评分={network_score:.0f}, "
                    f"延迟={avg_latency:.0f}ms, 带宽={bw_mbps:.1f}Mbps)"
                )
                changed = True

            if target_width != self.current_width:
                self.current_width = target_width
                self.logger.info(f"网络自适应: 宽度={target_width}")
                changed = True

            if target_fps != self.current_fps:
                self.current_fps = target_fps
                self.logger.info(f"网络自适应: 帧率={target_fps}")
                changed = True

            # ✅ 注意：带宽估算器的更新应该在 _network_monitor 中完成
            # 这里不要重复更新，避免重复计算

    def _calculate_frame_interval(self) -> float:
        """计算帧间隔"""
        network_quality = self.network_stats.network_quality

        if network_quality < 30:
            target_fps = self.config.min_fps
        elif network_quality > 80:
            target_fps = self.config.max_fps
        else:
            fps_range = self.config.max_fps - self.config.min_fps
            quality_factor = network_quality / 100.0
            target_fps = self.config.min_fps + fps_range * quality_factor

        return 1.0 / min(target_fps, self.current_fps)

    def _get_target_quality(self) -> int:
        """获取目标质量"""
        network_quality = self.network_stats.network_quality

        if network_quality < 30:
            return self.config.min_quality
        elif network_quality > 80:
            return self.config.max_quality
        else:
            quality_range = self.config.max_quality - self.config.min_quality
            return self.config.min_quality + int(
                quality_range * (network_quality / 100.0)
            )

    def _get_target_width(self) -> int:
        """获取目标宽度"""
        network_quality = self.network_stats.network_quality

        if network_quality < 30:
            return self.config.min_width
        elif network_quality > 80:
            return self.config.max_width
        else:
            width_range = self.config.max_width - self.config.min_width
            return self.config.min_width + int(width_range * (network_quality / 100.0))

    def _run_stats_loop(self):
        """统计循环"""
        while self.running and not self._stop_event.is_set():
            try:
                time.sleep(self.config.stats_report_interval)
                stats = self.get_stats()
                self.logger.info(
                    f"性能统计: fps={stats['fps_actual']:.1f}/{stats['fps_target']}, "
                    f"质量={stats['current_quality']}, 观众={stats['viewer_count']}, "
                    f"排除窗口={stats['excluded_windows_count']}"
                )
            except Exception as e:
                self.logger.debug(f"统计输出失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            avg_latency = 0
            if self.network_stats.round_trip_times:
                avg_latency = sum(self.network_stats.round_trip_times[-5:]) / min(
                    5, len(self.network_stats.round_trip_times)
                )

            avg_encode_time = 0
            if self.network_stats.encode_times:
                avg_encode_time = sum(self.network_stats.encode_times[-5:]) / min(
                    5, len(self.network_stats.encode_times)
                )

            return {
                "connected": self.state == ConnectionState.CONNECTED,
                "state": self.state.value,
                "viewer_count": self.viewer_count,
                "session_id": self.session_id,
                "current_quality": self.current_quality,
                "current_fps": self.current_fps,
                "current_width": self.current_width,
                "network_quality": self.network_stats.network_quality,
                "frames_sent": self.network_stats.frames_sent,
                "bytes_sent": self.network_stats.bytes_sent,
                "mb_sent": self.network_stats.bytes_sent / 1024 / 1024,
                "avg_frame_size_kb": self.network_stats.avg_frame_size / 1024,
                "avg_latency_ms": avg_latency,
                "avg_encode_time_ms": avg_encode_time,
                "dropped_frames": self.network_stats.dropped_frames,
                "reconnect_count": self.network_stats.reconnect_count,
                "fps_actual": self.performance_metrics.fps_actual,
                "fps_target": self.performance_metrics.fps_target,
                "capture_time_ms": self.performance_metrics.capture_time_ms,
                "encode_time_ms": self.performance_metrics.encode_time_ms,
                "exclusion_time_ms": self.performance_metrics.exclusion_time_ms,
                "active_regions": len(self._active_regions),
                "excluded_windows_count": len(self._excluded_regions),
                "window_exclusion_enabled": self.config.enable_window_exclusion,
            }

    def _get_stats_dict(self) -> Dict[str, Any]:
        """获取统计字典（用于心跳）"""
        with self._lock:
            return {
                "frames_sent": self.network_stats.frames_sent,
                "bytes_sent": self.network_stats.bytes_sent,
                "network_quality": self.network_stats.network_quality,
                "current_quality": self.current_quality,
                "current_fps": self.current_fps,
                "viewers": self.viewer_count,
                "excluded_windows": len(self._excluded_regions),
            }

    def update_client_info(self, client_id: str, employee_id: str):
        """更新客户端信息"""
        with self._lock:
            self.config.client_id = client_id
            self.config.employee_id = employee_id

            if self._pending_start and client_id:
                self._pending_start = False
                self.start()


def init_remote_screen(client):
    """初始化远程屏幕模块"""
    remote = RemoteScreenManager(client)
    client.remote_screen = remote
    return remote
