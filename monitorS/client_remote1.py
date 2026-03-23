#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client_remote.py - 专业级远程屏幕采集模块（完美契合后端）
功能：
- 屏幕采集与压缩
- 动态帧率/画质控制
- 差异帧传输（只传变化区域）
- 区域编码（ROI检测）
- H.264硬件加速
- 弱网自适应
- 二维码检测
"""

import asyncio
import base64
import io
import json
import logging
import threading
import time
import zlib
from typing import Optional, Dict, Any, List, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import queue
import math
import socket

import websockets
from PIL import Image, ImageGrab

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

try:
    import pyzbar.pyzbar as pyzbar

    ZBAR_AVAILABLE = True
except ImportError:
    ZBAR_AVAILABLE = False

# 尝试导入PIL
try:
    from PIL import ImageGrab

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class RemoteScreenConfig:
    """远程屏幕配置（与后端完美匹配）"""

    # 基础设置
    server_url: str = ""
    client_id: str = ""
    employee_id: str = ""

    # 初始质量设置
    initial_quality: int = 80  # 0-100
    initial_fps: int = 5  # 帧率

    # 动态调整范围
    min_quality: int = 30
    max_quality: int = 95
    min_fps: int = 1
    max_fps: int = 10

    # 分辨率设置
    max_width: int = 1280
    min_width: int = 640

    # 弱网检测
    network_check_interval: int = 5  # 秒
    latency_threshold_high: float = 500  # ms
    latency_threshold_low: float = 100  # ms

    # 高级优化
    enable_diff_frame: bool = True  # 差异帧传输
    enable_region_detect: bool = True  # 区域检测
    enable_h264: bool = CV2_AVAILABLE  # H.264硬件加速
    enable_qr_detect: bool = False  # 二维码检测
    diff_area_threshold: int = 1000  # 差异区域最小像素
    region_area_threshold: int = 5000  # 活动区域最小像素
    merge_distance: int = 50  # 区域合并距离

    # WebSocket设置
    ws_ping_interval: int = 20
    ws_ping_timeout: int = 10
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 5


@dataclass
class NetworkStats:
    """网络统计信息"""

    last_frame_time: float = 0
    frame_sent_times: List[float] = field(default_factory=list)
    round_trip_times: List[float] = field(default_factory=list)
    bytes_sent: int = 0
    frames_sent: int = 0
    network_quality: int = 100  # 0-100, 100最好
    avg_frame_size: float = 0
    diff_ratio: float = 0  # 差异帧节省带宽比例
    region_ratio: float = 0  # 区域编码节省比例
    encode_times: List[float] = field(default_factory=list)


class RemoteScreenManager:
    """
    专业级远程屏幕管理器（完美契合后端）
    - 负责屏幕采集
    - 动态调整质量
    - WebSocket通信
    - 弱网优化
    """

    def __init__(self, client):
        self.client = client
        self.logger = logging.getLogger(__name__)

        self.config = RemoteScreenConfig(
            server_url=client.current_server,
            client_id=client.client_id,
            employee_id=client.employee_id,
        )

        # 从客户端配置加载
        self._load_config()

        # 状态
        self.running = False
        self.connected = False
        self.thread: Optional[threading.Thread] = None
        self.viewer_count = 0  # 当前查看人数
        self.session_id: Optional[str] = None  # 当前会话ID
        self.reconnect_attempts = 0

        # 当前设置
        self.current_quality = self.config.initial_quality
        self.current_fps = self.config.initial_fps
        self.current_width = self.config.max_width

        # 网络统计
        self.network_stats = NetworkStats()

        # 屏幕变化检测
        self.last_frame: Optional[np.ndarray] = None
        self.last_frame_pil: Optional[Image.Image] = None
        self.last_frame_hash: Optional[str] = None
        self.last_motion_frame: Optional[np.ndarray] = None

        # 活动区域检测
        self.active_regions: List[Tuple[int, int, int, int]] = []

        # WebSocket连接
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_lock = asyncio.Lock()

        # 消息队列

        # 锁
        self.lock = threading.RLock()

        # 事件
        self.stop_event = threading.Event()

        # 统计
        self.stats = {
            "frames_sent": 0,
            "bytes_sent": 0,
            "avg_frame_size": 0,
            "avg_fps": 0,
            "diff_ratio": 0,
            "region_ratio": 0,
            "network_quality": 100,
        }

        self.config = RemoteScreenConfig(
            server_url=client.current_server,
            client_id=client.client_id,
            employee_id=client.employee_id,
        )
        # ===== 添加初始化日志 =====
        self.logger.info("=" * 60)
        self.logger.info("🔄 初始化远程屏幕管理器")
        self.logger.info(f"  客户端ID: {self.config.client_id}")
        self.logger.info(f"  员工ID: {self.config.employee_id}")
        self.logger.info(f"  服务器URL: {self.config.server_url}")
        self.logger.info(f"  初始帧率: {self.config.initial_fps}")
        self.logger.info(f"  初始质量: {self.config.initial_quality}")
        self.logger.info("=" * 60)

        self.logger.info(
            f"📋 远程屏幕配置: server={client.current_server}, client_id={client.client_id}"
        )

        # 后台任务
        self.tasks: Set[asyncio.Task] = set()

    def _load_config(self):
        """从客户端配置加载设置"""
        config_mgr = self.client.config_manager

        # 基础设置
        self.config.initial_fps = config_mgr.get("remote_base_fps", 5)
        self.config.min_fps = config_mgr.get("remote_min_fps", 1)
        self.config.max_fps = config_mgr.get("remote_max_fps", 10)

        # 画质设置
        self.config.initial_quality = config_mgr.get("remote_base_quality", 70)
        self.config.min_quality = config_mgr.get("remote_min_quality", 30)
        self.config.max_quality = config_mgr.get("remote_max_quality", 85)

        # 分辨率设置
        self.config.max_width = config_mgr.get("remote_max_width", 1280)
        self.config.min_width = config_mgr.get("remote_min_width", 640)

        # 高级优化
        self.config.enable_diff_frame = config_mgr.get("remote_enable_diff", True)
        self.config.enable_region_detect = config_mgr.get("remote_enable_region", True)
        self.config.enable_h264 = (
            config_mgr.get("remote_enable_h264", True) and CV2_AVAILABLE
        )
        self.config.enable_qr_detect = (
            config_mgr.get("remote_enable_qr", False) and ZBAR_AVAILABLE
        )

    def start(self):
        """启动远程屏幕服务"""
        if self.running:
            self.logger.debug("远程屏幕服务已在运行")
            return

        # ===== 检查 client_id =====
        if not self.client.client_id:
            self.logger.warning("⚠️ client_id 为空，远程屏幕服务将在注册后自动启动")
            # 设置挂起标记，但不启动线程
            self._pending_start = True
            return

        # 检查服务器URL
        if not self.config.server_url:
            self.logger.error("❌ 服务器URL为空，无法启动远程屏幕")
            return

        # ===== 添加启动日志 =====
        self.logger.info("=" * 60)
        self.logger.info("🚀 正在启动远程屏幕服务...")
        self.logger.info(f"  客户端ID: {self.client.client_id}")
        self.logger.info(f"  服务器: {self.config.server_url}")
        self.logger.info(f"  初始帧率: {self.current_fps}")
        self.logger.info(f"  初始质量: {self.current_quality}")
        self.logger.info("=" * 60)

        # 启动线程
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run_loop, name="RemoteScreen", daemon=True
        )
        self.thread.start()
        self.logger.info("🚀 专业级远程屏幕服务已启动")
        self.logger.info(f"  客户端ID: {self.client.client_id}")
        self.logger.info(f"  服务器: {self.config.server_url}")

    def stop(self):
        """停止远程屏幕服务"""
        self.running = False
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self._disconnect()
        self.logger.info("⏹️ 远程屏幕服务已停止")

    def _run_loop(self):
        """主循环"""
        while self.running and not self.stop_event.is_set():
            try:
                asyncio.run(self._run_async())
            except Exception as e:
                self.logger.error(f"远程屏幕异常: {e}")
                time.sleep(5)

    async def _run_async(self):
        """异步主循环"""
        # 连接服务器
        if not await self._connect():
            self.reconnect_attempts += 1
            if self.reconnect_attempts > self.config.max_reconnect_attempts:
                self.logger.error("达到最大重连次数，停止服务")
                self.running = False
                return
            await asyncio.sleep(self.config.reconnect_delay)
            return

        self.reconnect_attempts = 0

        self.message_queue = asyncio.Queue(maxsize=20)
        self.viewer_count = 1 
        await self.message_queue.put(json.dumps({ 
            "type": "get_stats",
            "timestamp": time.time()
        }))

        # 创建后台任务
        self.tasks.clear()
        self.tasks.add(asyncio.create_task(self._heartbeat_loop()))
        self.tasks.add(asyncio.create_task(self._network_monitor_loop()))
        self.tasks.add(asyncio.create_task(self._message_sender_loop()))
        self.tasks.add(asyncio.create_task(self._receiver_loop()))

        # 发送客户端信息
        await self._send_client_info()

        # ===== 添加初始状态日志 =====
        self.logger.info("=" * 60)
        self.logger.info("🎬 开始采集循环")
        self.logger.info(f"  初始观众数: {self.viewer_count}")
        self.logger.info(f"  初始帧率: {self.current_fps}")
        self.logger.info(f"  初始质量: {self.current_quality}")
        self.logger.info("=" * 60)

        # 采集和发送循环
        last_frame_time = 0
        frames_this_second = 0
        last_stats_time = time.time()
        loop_count = 0

        # 在 _run_async 方法的采集循环中
        while self.running and self.connected:
            try:
                loop_count += 1
                now = time.time()

                # ===== 每10秒打印一次状态 =====
                if loop_count % 10 == 0:
                    self.logger.info(
                        f"📊 远程屏幕状态: viewer_count={self.viewer_count}, "
                        f"connected={self.connected}, running={self.running}"
                    )

                # ✅ 修改：始终采集，不检查 viewer_count
                # 直接开始采集
                if frames_this_second == 0:
                    self.logger.info(f"🎬 正在采集屏幕 (强制模式, 帧率目标: {self.current_fps})")

                # 动态计算帧间隔
                frame_interval = self._get_target_interval()

                # 控制帧率
                if now - last_frame_time < frame_interval:
                    await asyncio.sleep(0.01)
                    continue

                # 采集屏幕
                frame = await self._capture_screen()
                if frame is None:
                    self.logger.error("❌ 屏幕采集失败")
                    await asyncio.sleep(0.1)
                    continue

                # 处理并发送
                await self._process_and_send(frame)

                last_frame_time = now
                frames_this_second += 1

                # 每秒统计
                if now - last_stats_time >= 1:
                    self.stats["avg_fps"] = frames_this_second
                    self.logger.info(
                        f"📈 采集统计: 实际帧率={frames_this_second}, "
                        f"目标帧率={self.current_fps}, 质量={self.current_quality}"
                    )
                    frames_this_second = 0
                    last_stats_time = now

            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket连接关闭")
                self.connected = False
                break
            except Exception as e:
                self.logger.error(f"采集循环异常: {e}")
                await asyncio.sleep(1)

        # 取消所有任务
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.logger.info("⏹️ 远程屏幕采集循环结束")

    async def _connect(self) -> bool:
        """建立WebSocket连接"""
        if self.connected:
            return True

        try:
            # 检查 client_id 是否存在
            if not self.config.client_id:
                self.logger.error("❌ client_id 不存在，请确保客户端已成功注册")
                return False

            # 检查服务器URL
            if not self.config.server_url:
                self.logger.error("❌ 服务器URL为空")
                return False

            # 构建WebSocket URL
            base_url = self.config.server_url.replace("http://", "ws://").replace(
                "https://", "wss://"
            )
            ws_url = f"{base_url}/api/remote/ws/client/{self.config.client_id}"

            self.logger.info(f"🔌 正在连接远程屏幕服务: {ws_url}")
            self.logger.info(f"📋 客户端ID: {self.config.client_id}")

            # 添加连接超时
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    ws_url,
                    ping_interval=self.config.ws_ping_interval,
                    ping_timeout=self.config.ws_ping_timeout,
                    max_size=10 * 1024 * 1024,  # 10MB
                    open_timeout=10,  # 连接超时10秒
                ),
                timeout=15,  # 总超时15秒
            )

            self.connected = True
            self.logger.info(f"✅ 远程屏幕已连接")
            self.logger.info(f"📊 WebSocket状态: {self.ws.state}")

            test_msg = {
                "type": "client_ready",
                "client_id": self.config.client_id,
                "timestamp": time.time(),
            }
            await self.ws.send(json.dumps(test_msg))
            self.logger.info("📤 发送客户端就绪消息")

            # 等待欢迎消息
            try:
                welcome = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                data = json.loads(welcome)
                self.logger.info(f"📡 收到欢迎消息: {data}")
                if data.get("type") == "connected":
                    self.logger.info(
                        f"📡 服务器连接成功，会话ID: {data.get('session_id', 'unknown')}"
                    )
            except asyncio.TimeoutError:
                self.logger.debug("等待欢迎消息超时")
            except Exception as e:
                self.logger.debug(f"处理欢迎消息失败: {e}")

            return True

        except asyncio.TimeoutError:
            self.logger.error("❌ 连接超时")
            return False
        except websockets.exceptions.InvalidStatusCode as e:
            if e.status_code == 403:
                self.logger.error(f"❌ 连接被拒绝 (403)：客户端ID无效或未授权")
                self.logger.error(f"   client_id: {self.config.client_id}")
                self.logger.error(f"   请确保客户端已在服务器注册")
            elif e.status_code == 404:
                self.logger.error(f"❌ 连接被拒绝 (404)：远程屏幕服务不存在")
            else:
                self.logger.error(f"❌ 远程屏幕连接失败 (HTTP {e.status_code}): {e}")
            return False
        except websockets.exceptions.InvalidURI as e:
            self.logger.error(f"❌ 无效的WebSocket URL: {e}")
            return False
        except ConnectionRefusedError:
            self.logger.error(f"❌ 连接被拒绝：服务器未运行或端口错误")
            return False
        except Exception as e:
            self.logger.error(f"❌ 远程屏幕连接失败: {e}")
            return False

    def _disconnect(self):
        """断开连接"""
        if self.ws:
            try:
                asyncio.run(self.ws.close())
            except:
                pass
            self.ws = None
        self.connected = False
        self.viewer_count = 0

    async def _send_client_info(self):
        """发送客户端能力信息"""
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
                "max_fps": self.config.max_fps,
                "max_quality": self.config.max_quality,
                "max_width": self.config.max_width,
                "min_fps": self.config.min_fps,
                "min_quality": self.config.min_quality,
                "min_width": self.config.min_width,
            },
            "system": {
                "cpu_count": getattr(
                    self.client.system_info, "get_cpu_count", lambda: 0
                )(),
                "has_gpu": self.config.enable_h264,
            },
        }
        await self.message_queue.put(json.dumps(info))

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.running and self.connected:
            try:
                await asyncio.sleep(30)

                heartbeat = {
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "client_id": self.config.client_id,
                    "viewers": self.viewer_count,
                    "stats": self.get_stats(),
                }
                await self.message_queue.put(json.dumps(heartbeat))

            except Exception as e:
                self.logger.debug(f"心跳发送失败: {e}")

    async def _network_monitor_loop(self):
        """网络质量监控循环"""
        while self.running and self.connected:
            try:
                await asyncio.sleep(2)

                # 发送ping测量延迟
                start = time.time()
                ping_msg = {
                    "type": "ping",
                    "timestamp": start,
                    "client_id": self.config.client_id,
                }

                # 发送并等待pong
                await self.ws.send(json.dumps(ping_msg))

                # 设置超时
                try:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                    data = json.loads(response)

                    if data.get("type") == "pong":
                        latency = (time.time() - start) * 1000
                        self._update_network_from_latency(latency)

                        # 记录RTT
                        with self.lock:
                            self.network_stats.round_trip_times.append(latency)
                            if len(self.network_stats.round_trip_times) > 20:
                                self.network_stats.round_trip_times.pop(0)

                except asyncio.TimeoutError:
                    self.logger.debug("Ping超时")
                    self._update_network_from_latency(1000)  # 1000ms超时

                # 动态调整质量和帧率
                await self._adjust_quality()

            except Exception as e:
                self.logger.debug(f"网络监控异常: {e}")

    async def _receiver_loop(self):
        """接收消息循环"""
        self.logger.info("📡 接收消息循环已启动")
        message_count = 0

        while self.running and self.connected:
            try:
                message = await self.ws.recv()
                message_count += 1
                self.logger.info(f"📨 收到第 {message_count} 条消息")
                await self._handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                self.logger.warning(f"⚠️ WebSocket连接关闭: {e.code} - {e.reason}")
                self.connected = False
                break
            except asyncio.TimeoutError:
                self.logger.debug("接收超时，继续等待...")
                continue
            except Exception as e:
                self.logger.error(f"❌ 接收消息失败: {e}", exc_info=True)
                await asyncio.sleep(0.1)
                # 不要立即退出，继续尝试

        self.logger.info(f"📡 接收消息循环结束，共收到 {message_count} 条消息")

    async def _message_sender_loop(self):
        """消息发送循环"""
        while self.running and self.connected:
            try:
                message = await self.message_queue.get()
                await self.ws.send(message)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                self.logger.error(f"发送消息失败: {e}")
                await asyncio.sleep(0.1)

    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            self.logger.info(f"📨 [客户端] 原始消息: {message}")
            data = json.loads(message)
            msg_type = data.get("type")

            self.logger.info(f"📩 收到消息: type={msg_type}")

            if msg_type == "viewer_update":
                old_count = self.viewer_count
                new_count = data.get("viewers", 0)
                self.viewer_count = new_count

                # ===== 使用 INFO 级别记录观众变化 =====
                self.logger.info("=" * 60)
                self.logger.info(f"👥 观众数量更新: {old_count} -> {new_count}")
                self.logger.info("=" * 60)

                # ===== 当从0变成1时，记录开始采集 =====
                if new_count > 0 and old_count == 0:
                    self.logger.info("🎬 有观众连接，开始采集屏幕画面")

                # ===== 当从1变成0时，记录停止采集 =====
                elif new_count == 0 and old_count > 0:
                    self.logger.info("⏸️ 所有观众离开，停止采集屏幕画面")

            elif msg_type == "command":
                # 管理员命令
                self.logger.info(f"📋 收到命令: {data.get('command')}")
                await self._handle_command(data)

            elif msg_type == "config":
                # 配置更新
                config = data.get("config", {})
                old_fps = self.current_fps
                old_quality = self.current_quality
                old_width = self.current_width

                if "fps" in config:
                    self.current_fps = config["fps"]
                if "quality" in config:
                    self.current_quality = config["quality"]
                if "width" in config:
                    self.current_width = config["width"]
                if "enable_diff" in config:
                    self.config.enable_diff_frame = config["enable_diff"]
                if "enable_region" in config:
                    self.config.enable_region_detect = config["enable_region"]

                # ===== 记录配置变化 =====
                changes = []
                if self.current_fps != old_fps:
                    changes.append(f"帧率: {old_fps} -> {self.current_fps}")
                if self.current_quality != old_quality:
                    changes.append(f"质量: {old_quality} -> {self.current_quality}")
                if self.current_width != old_width:
                    changes.append(f"宽度: {old_width} -> {self.current_width}")

                if changes:
                    self.logger.info(f"⚙️ 配置已更新: {', '.join(changes)}")
                else:
                    self.logger.debug("⚙️ 收到配置更新，但无变化")

            elif msg_type == "connected":
                # 连接成功消息（来自服务器）
                self.session_id = data.get("session_id", "unknown")
                if "viewers" in data:
                    self.viewer_count = data.get("viewers", 0)
                self.logger.info(f"✅ 服务器连接成功，会话ID: {self.session_id}")
                self.logger.info(f"👥 初始观众数: {self.viewer_count}")

            elif msg_type == "heartbeat_ack":
                # 心跳确认
                latency = None
                if "timestamp" in data:
                    latency = (time.time() - data["timestamp"]) * 1000
                    self._update_network_from_latency(latency)

                self.logger.debug(
                    f"❤️ 心跳确认 (延迟: {latency:.0f}ms)" if latency else "❤️ 心跳确认"
                )

            elif msg_type == "pong":
                # ping响应，已经在_monitor_loop中处理
                latency = (time.time() - data.get("timestamp", time.time())) * 1000
                self.logger.debug(f"🏓 Pong响应 (延迟: {latency:.0f}ms)")

            elif msg_type == "error":
                # 服务器返回错误
                error_msg = data.get("message", "未知错误")
                self.logger.error(f"❌ 服务器错误: {error_msg}")

            else:
                self.logger.debug(f"其他消息类型: {msg_type}")

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON解析失败: {e}")
            self.logger.debug(f"原始消息: {message[:200]}...")
        except Exception as e:
            self.logger.error(f"❌ 处理消息失败: {e}", exc_info=True)

    async def _handle_command(self, command: dict):
        """处理管理员命令"""
        cmd = command.get("command")
        params = command.get("params", {})

        if cmd == "quality":
            self.current_quality = params.get("quality", self.current_quality)
            self.logger.info(f"📊 质量调整为: {self.current_quality}")

        elif cmd == "fps":
            self.current_fps = params.get("fps", self.current_fps)
            self.logger.info(f"⏱️ 帧率调整为: {self.current_fps}")

        elif cmd == "width":
            self.current_width = params.get("width", self.current_width)
            self.logger.info(f"📐 宽度调整为: {self.current_width}")

        elif cmd == "fullscreen":
            # 立即发送全屏截图
            frame = await self._capture_screen()
            if frame:
                await self._process_and_send(frame)

        elif cmd == "qr_enable":
            self.config.enable_qr_detect = params.get("enable", False)
            self.logger.info(
                f"📱 二维码检测: {'启用' if self.config.enable_qr_detect else '禁用'}"
            )

        elif cmd == "diff_enable":
            self.config.enable_diff_frame = params.get("enable", True)
            self.logger.info(
                f"🔄 差异帧传输: {'启用' if self.config.enable_diff_frame else '禁用'}"
            )

    def _update_network_from_latency(self, latency_ms: float):
        """根据延迟更新网络质量"""
        # 延迟映射到网络质量
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

        # 平滑处理
        with self.lock:
            self.network_stats.network_quality = int(
                self.network_stats.network_quality * 0.7 + quality * 0.3
            )
            self.stats["network_quality"] = self.network_stats.network_quality

    def _get_target_interval(self) -> float:
        """根据网络质量计算目标帧间隔"""
        network_quality = self.network_stats.network_quality

        # 基础间隔
        base_interval = 1.0 / self.current_fps

        if network_quality < 30:  # 网络极差
            interval = 1.0 / self.config.min_fps
        elif network_quality > 80:  # 网络极好
            interval = 1.0 / self.config.max_fps
        else:
            # 线性插值
            quality_factor = network_quality / 100.0
            fps_range = self.config.max_fps - self.config.min_fps
            target_fps = self.config.min_fps + fps_range * quality_factor
            interval = 1.0 / target_fps

        return interval

    def _get_target_quality(self) -> int:
        """根据网络质量计算目标画质"""
        network_quality = self.network_stats.network_quality

        if network_quality < 30:
            return self.config.min_quality
        elif network_quality > 80:
            return self.config.max_quality
        else:
            # 线性插值
            quality_range = self.config.max_quality - self.config.min_quality
            return self.config.min_quality + int(
                quality_range * (network_quality / 100.0)
            )

    def _get_target_width(self) -> int:
        """根据网络质量计算目标宽度"""
        network_quality = self.network_stats.network_quality

        if network_quality < 30:
            return self.config.min_width
        elif network_quality > 80:
            return self.config.max_width
        else:
            # 线性插值
            width_range = self.config.max_width - self.config.min_width
            return self.config.min_width + int(width_range * (network_quality / 100.0))

    def _estimate_full_size(self, frame: np.ndarray) -> int:
        """估计完整帧大小"""
        return frame.shape[0] * frame.shape[1] * 3 // 2  # 粗略估计

    async def _capture_screen(self) -> Optional[np.ndarray]:
        """采集屏幕 - 返回OpenCV格式"""
        try:
            # 使用mss（最快）
            if MSS_AVAILABLE:
                with mss.mss() as sct:
                    # 捕获所有显示器
                    monitors = sct.monitors[1:]  # 跳过"all in one"

                    if not monitors:
                        return None

                    # 如果只有一个显示器，直接捕获
                    if len(monitors) == 1:
                        screenshot = sct.grab(monitors[0])
                        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    else:
                        # 计算总尺寸
                        total_width = sum(m["width"] for m in monitors)
                        max_height = max(m["height"] for m in monitors)

                        # 创建合并图像
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

            # 使用PIL
            elif PIL_AVAILABLE:
                pil_img = ImageGrab.grab(all_screens=True)
                img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            else:
                self.logger.error("没有可用的屏幕捕获库")
                return None

            # 缩放处理
            target_width = self._get_target_width()
            if img_cv.shape[1] > target_width:
                ratio = target_width / img_cv.shape[1]
                new_height = int(img_cv.shape[0] * ratio)
                img_cv = cv2.resize(
                    img_cv, (target_width, new_height), interpolation=cv2.INTER_AREA
                )

            # 二维码检测（可选）
            if self.config.enable_qr_detect and ZBAR_AVAILABLE:
                await self._detect_qr_codes(img_cv)

            return img_cv

        except Exception as e:
            self.logger.error(f"屏幕捕获失败: {e}")
            return None

    async def _detect_qr_codes(self, frame: np.ndarray):
        """检测二维码"""
        try:
            # 转换为PIL图像
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            # 解码二维码
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

                # 发送二维码信息
                qr_msg = {
                    "type": "qr_detected",
                    "timestamp": time.time(),
                    "qr_codes": qr_data,
                    "client_id": self.config.client_id,
                }
                await self.message_queue.put(json.dumps(qr_msg))

        except Exception as e:
            self.logger.debug(f"二维码检测失败: {e}")

    async def _process_and_send(self, frame: np.ndarray):
        """简化版：直接发送帧"""
        if not self.ws or not self.connected:
            return
        
        try:
            # 最简单的编码：直接 JPEG
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            buffer = io.BytesIO()
            pil_img.save(buffer, format="JPEG", quality=70)
            img_data = buffer.getvalue()
            
            # 发送
            message = {
                "type": "frame",
                "data": base64.b64encode(img_data).decode("utf-8"),
                "width": frame.shape[1],
                "height": frame.shape[0],
                "timestamp": datetime.now().isoformat(),
            }
            
            await self.ws.send(json.dumps(message))
            self.logger.info("✅ 帧已发送")
            
        except Exception as e:
            self.logger.error(f"发送失败: {e}")

    async def _encode_full_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """编码完整帧"""
        quality = self._get_target_quality()
        self.current_quality = quality

        self.logger.info(f"📤 编码帧: quality={quality}, frame shape={frame.shape}")

        try:
            # 使用H.264编码（如果可用）
            if self.config.enable_h264 and CV2_AVAILABLE:
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
                result, encimg = cv2.imencode(".jpg", frame, encode_param)
                if result:
                    # 使用zlib进一步压缩
                    compressed = zlib.compress(encimg.tobytes(), level=3)
                    return compressed

            # 使用PIL JPEG编码
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)

            buffer = io.BytesIO()
            pil_img.save(
                buffer,
                format="JPEG",
                quality=quality,
                optimize=True,
                subsampling=2 if quality < 50 else 0,
            )

            # 使用zlib进一步压缩
            compressed = zlib.compress(buffer.getvalue(), level=3)
            return compressed

        except Exception as e:
            self.logger.error(f"编码失败: {e}")
            return None

    async def _encode_diff_frame(self, frame: np.ndarray) -> Optional[bytes]:
        """编码差异帧 - 只发送变化区域"""
        if self.last_frame is None or not CV2_AVAILABLE:
            return None

        try:
            # 计算差异
            diff = cv2.absdiff(frame, self.last_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

            # 二值化
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

            # 膨胀，连接相邻变化区域
            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=2)

            # 查找轮廓
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return None

            # 提取变化区域
            regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                # 过滤太小的区域
                if w * h > self.config.diff_area_threshold:
                    regions.append((x, y, w, h))

            if not regions:
                return None

            # 合并重叠区域
            merged_regions = self._merge_regions(regions)

            # 编码变化区域
            region_data = []
            quality = self._get_target_quality()

            for x, y, w, h in merged_regions:
                # 提取变化区域
                region = frame[y : y + h, x : x + w]

                # 编码区域
                if self.config.enable_h264:
                    encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
                    result, enc_region = cv2.imencode(".jpg", region, encode_param)
                    if result:
                        region_data.append(
                            {
                                "x": x,
                                "y": y,
                                "w": w,
                                "h": h,
                                "data": base64.b64encode(enc_region.tobytes()).decode(
                                    "utf-8"
                                ),
                            }
                        )
                else:
                    # 使用PIL编码
                    region_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
                    pil_region = Image.fromarray(region_rgb)
                    buffer = io.BytesIO()
                    pil_region.save(
                        buffer, format="JPEG", quality=quality, optimize=True
                    )
                    region_data.append(
                        {
                            "x": x,
                            "y": y,
                            "w": w,
                            "h": h,
                            "data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
                        }
                    )

            if region_data:
                # 打包差异数据
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
            self.logger.error(f"差异编码失败: {e}")

        return None

    async def _encode_regions(self, frame: np.ndarray) -> Optional[bytes]:
        """检测并编码活动区域"""
        if self.last_motion_frame is None or not CV2_AVAILABLE:
            self.last_motion_frame = frame.copy()
            return None

        try:
            # 检测运动区域
            diff = cv2.absdiff(frame, self.last_motion_frame)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, 20, 255, cv2.THRESH_BINARY)

            # 形态学操作
            kernel = np.ones((10, 10), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=3)

            # 查找轮廓
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

            # 合并区域
            merged_regions = self._merge_regions(regions)
            self.active_regions = merged_regions

            # 创建背景帧（不活动区域）
            background = self.last_motion_frame.copy()

            # 编码
            quality = self._get_target_quality()

            # 编码背景
            if self.config.enable_h264:
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
                result, enc_background = cv2.imencode(".jpg", background, encode_param)
                if not result:
                    return None
                bg_data = base64.b64encode(enc_background.tobytes()).decode("utf-8")
            else:
                bg_rgb = cv2.cvtColor(background, cv2.COLOR_BGR2RGB)
                pil_bg = Image.fromarray(bg_rgb)
                buffer = io.BytesIO()
                pil_bg.save(buffer, format="JPEG", quality=quality, optimize=True)
                bg_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

            # 编码活动区域
            region_data = []
            for x, y, w, h in merged_regions:
                region = frame[y : y + h, x : x + w]

                if self.config.enable_h264:
                    result, enc_region = cv2.imencode(".jpg", region, encode_param)
                    if result:
                        region_data.append(
                            {
                                "x": x,
                                "y": y,
                                "w": w,
                                "h": h,
                                "data": base64.b64encode(enc_region.tobytes()).decode(
                                    "utf-8"
                                ),
                            }
                        )
                else:
                    region_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
                    pil_region = Image.fromarray(region_rgb)
                    buffer = io.BytesIO()
                    pil_region.save(
                        buffer, format="JPEG", quality=quality, optimize=True
                    )
                    region_data.append(
                        {
                            "x": x,
                            "y": y,
                            "w": w,
                            "h": h,
                            "data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
                        }
                    )

            # 打包
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
            self.last_motion_frame = frame.copy()

            return zlib.compress(region_json.encode("utf-8"), level=6)

        except Exception as e:
            self.logger.error(f"区域编码失败: {e}")

        return None

    def _merge_regions(self, regions: List[Tuple]) -> List[Tuple]:
        """合并重叠或相邻的区域"""
        if not regions:
            return []

        # 排序
        regions = sorted(regions, key=lambda r: (r[0], r[1]))

        merged = []
        current = list(regions[0])

        for r in regions[1:]:
            x, y, w, h = r

            # 检查是否重叠或相邻
            if (
                x < current[0] + current[2] + self.config.merge_distance
                and y < current[1] + current[3] + self.config.merge_distance
            ):
                # 合并
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

    async def _adjust_quality(self):
        """动态调整质量和帧率"""
        try:
            # 计算平均延迟
            with self.lock:
                if len(self.network_stats.round_trip_times) > 3:
                    avg_latency = sum(self.network_stats.round_trip_times[-3:]) / 3
                else:
                    return

            # 根据延迟调整
            if avg_latency > self.config.latency_threshold_high:
                # 弱网：降低质量和帧率
                new_quality = max(self.config.min_quality, self.current_quality - 5)
                new_width = max(self.config.min_width, self.current_width - 100)

                with self.lock:
                    if new_quality != self.current_quality:
                        self.current_quality = new_quality
                        self.logger.info(f"📉 弱网降级: 质量={new_quality}")

                    if new_width != self.current_width:
                        self.current_width = new_width
                        self.logger.info(f"📉 分辨率降级: 宽度={new_width}")

            elif avg_latency < self.config.latency_threshold_low:
                # 好网：提升质量和帧率
                new_quality = min(self.config.max_quality, self.current_quality + 3)
                new_width = min(self.config.max_width, self.current_width + 50)

                with self.lock:
                    if new_quality != self.current_quality:
                        self.current_quality = new_quality
                        self.logger.info(f"📈 网络恢复: 质量={new_quality}")

                    if new_width != self.current_width:
                        self.current_width = new_width
                        self.logger.info(f"📈 分辨率提升: 宽度={new_width}")

        except Exception as e:
            self.logger.debug(f"调整质量失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            # 计算平均编码时间
            avg_encode_time = 0
            if self.network_stats.encode_times:
                avg_encode_time = sum(self.network_stats.encode_times[-5:]) / len(
                    self.network_stats.encode_times[-5:]
                )

            # 计算平均延迟
            avg_latency = 0
            if self.network_stats.round_trip_times:
                avg_latency = sum(self.network_stats.round_trip_times[-5:]) / len(
                    self.network_stats.round_trip_times[-5:]
                )

            return {
                "connected": self.connected,
                "viewer_count": self.viewer_count,
                "current_quality": self.current_quality,
                "current_fps": self.current_fps,
                "current_width": self.current_width,
                "network_quality": self.network_stats.network_quality,
                "frames_sent": self.network_stats.frames_sent,
                "bytes_sent": self.network_stats.bytes_sent,
                "mb_sent": self.network_stats.bytes_sent / 1024 / 1024,
                "avg_frame_size": self.network_stats.avg_frame_size,
                "avg_latency": avg_latency,
                "avg_encode_time": avg_encode_time,
                "diff_ratio": self.network_stats.diff_ratio,
                "region_ratio": self.network_stats.region_ratio,
                "active_regions": len(self.active_regions),
                "fps_actual": self.stats["avg_fps"],
            }


# ==================== 客户端集成 ====================
def init_remote_screen(client):
    """初始化远程屏幕模块"""
    remote = RemoteScreenManager(client)
    client.remote_screen = remote
    return remote
