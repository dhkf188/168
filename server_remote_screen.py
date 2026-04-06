#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server_remote_screen.py - 专业级远程屏幕查看服务（企业增强版）
功能：
- WebSocket实时推送屏幕画面（支持压缩）
- 会话管理（多会话支持）
- 权限控制
- 弱网自适应配置下发
- 二维码检测数据转发
- 完整的统计和监控
- 发送队列和批量统计优化
- 帧数据压缩传输
- 断线重连机制
- 会话恢复功能
"""

import asyncio
import base64
import json
import logging
import time
import zlib
import urllib.parse
import re
import hashlib
import secrets
from typing import Dict, Optional, Set, Any, List, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from functools import wraps
from enum import Enum

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    status,
)
from fastapi.websockets import WebSocketState
from sqlalchemy.orm import Session
from jose import jwt, JWTError, ExpiredSignatureError

from server_database import get_db
from server_auth import get_current_active_user
from server_config import Config
import server_models as models
from server_timezone import get_beijing_now

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/remote", tags=["远程屏幕"])


# ==================== 常量定义 ====================
# WebSocket配置
WS_MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10MB
WS_MAX_FRAME_SIZE = 5 * 1024 * 1024  # 5MB（单帧最大5MB）
WS_HEARTBEAT_INTERVAL = 15  # 心跳间隔（秒）
WS_IDLE_TIMEOUT = 60  # 空闲超时（秒）
WS_SEND_TIMEOUT = 3  # 发送超时（秒）
WS_SEND_QUEUE_SIZE = 100  # 发送队列大小

# 会话清理配置
CLEANUP_INTERVAL = 10  # 清理间隔（秒）
HEARTBEAT_TIMEOUT = 20  # 心跳超时（秒）
MAX_SESSION_AGE = 3600  # 最大会话时长（秒）
MAX_FRAME_IDLE = 30  # 最大帧空闲时间（秒）

# 帧统计配置
FRAME_STATS_INTERVAL = 0.1  # 帧统计更新间隔（秒）
FRAME_STATS_BATCH = 10  # 批量更新帧数
VIEWER_UPDATE_COOLDOWN = 1.0  # 观众更新冷却时间（秒）

# 压缩配置
COMPRESSION_ENABLED = True  # 是否启用压缩
COMPRESSION_LEVEL = 6  # 压缩级别 (1-9, 6是平衡)
COMPRESSION_MIN_SIZE = 1024  # 最小压缩大小（字节）
COMPRESSION_THRESHOLD = 0.7  # 压缩阈值（压缩后小于原大小的比例才使用）

# 断线重连配置
RECONNECT_TOKEN_EXPIRY = 30  # 重连令牌有效期（秒）
SESSION_RECOVERY_TIMEOUT = 30  # 会话恢复超时（秒）
MAX_RECONNECT_ATTEMPTS = 3  # 最大重连尝试次数

# 配置字段白名单（带范围验证）
ALLOWED_CONFIG_FIELDS = {
    "quality": (int, 1, 100),
    "fps": (int, 1, 30),
    "width": (int, 320, 3840),
    "height": (int, 240, 2160),
    "enable_diff": bool,
    "enable_region": bool,
    "enable_h264": bool,
    "enable_qr": bool,
    "network_quality": (int, 1, 100),
    "enable_compression": bool,  # 新增：是否启用压缩
    "compression_level": (int, 1, 9),  # 新增：压缩级别
}


class ReconnectStatus(Enum):
    """重连状态"""

    NONE = "none"
    PENDING = "pending"
    RECOVERED = "recovered"
    FAILED = "failed"


# ==================== 压缩工具 ====================
class FrameCompressor:
    """帧数据压缩器"""

    @staticmethod
    def compress(data: str, level: int = COMPRESSION_LEVEL) -> Tuple[bytes, bool]:
        """
        压缩数据
        返回: (压缩后的数据, 是否压缩成功)
        """
        if not COMPRESSION_ENABLED:
            return data.encode("utf-8"), False

        original_size = len(data)
        if original_size < COMPRESSION_MIN_SIZE:
            return data.encode("utf-8"), False

        try:
            compressed = zlib.compress(data.encode("utf-8"), level)
            compressed_size = len(compressed)

            # 如果压缩后大小超过原大小的压缩阈值，不采用压缩
            if compressed_size / original_size > COMPRESSION_THRESHOLD:
                return data.encode("utf-8"), False

            return compressed, True
        except Exception as e:
            logger.warning(f"压缩失败: {e}")
            return data.encode("utf-8"), False

    @staticmethod
    def decompress(data: bytes) -> str:
        """解压数据"""
        try:
            # 尝试解压
            decompressed = zlib.decompress(data)
            return decompressed.decode("utf-8")
        except zlib.error:
            # 如果不是压缩数据，直接解码
            return data.decode("utf-8")
        except Exception as e:
            logger.error(f"解压失败: {e}")
            raise


# ==================== 断线重连管理器 ====================
class ReconnectManager:
    """断线重连管理器"""

    def __init__(self):
        self._reconnect_tokens: Dict[str, Dict] = (
            {}
        )  # token -> {session_id, employee_id, client_id, admin_user, expiry}
        self._pending_reconnections: Dict[str, Dict] = (
            {}
        )  # session_id -> reconnect_data
        self._session_recovery_data: Dict[str, Dict] = {}  # session_id -> recovery_data
        self._lock = asyncio.Lock()

    def generate_reconnect_token(
        self, session_id: str, employee_id: str, client_id: str, admin_user: str
    ) -> str:
        """生成重连令牌"""
        token_data = {
            "session_id": session_id,
            "employee_id": employee_id,
            "client_id": client_id,
            "admin_user": admin_user,
            "expiry": time.time() + RECONNECT_TOKEN_EXPIRY,
            "token": secrets.token_urlsafe(32),
        }

        token = token_data["token"]
        self._reconnect_tokens[token] = token_data
        return token

    async def validate_reconnect_token(self, token: str) -> Optional[Dict]:
        """验证重连令牌"""
        async with self._lock:
            token_data = self._reconnect_tokens.get(token)
            if not token_data:
                return None

            if time.time() > token_data["expiry"]:
                del self._reconnect_tokens[token]
                return None

            return token_data

    async def store_recovery_data(self, session_id: str, recovery_data: Dict):
        """存储会话恢复数据"""
        async with self._lock:
            self._session_recovery_data[session_id] = {
                "data": recovery_data,
                "expiry": time.time() + SESSION_RECOVERY_TIMEOUT,
            }

    async def get_recovery_data(self, session_id: str) -> Optional[Dict]:
        """获取会话恢复数据"""
        async with self._lock:
            data = self._session_recovery_data.get(session_id)
            if data and time.time() < data["expiry"]:
                return data["data"]
            return None

    async def clear_recovery_data(self, session_id: str):
        """清理会话恢复数据"""
        async with self._lock:
            self._session_recovery_data.pop(session_id, None)

    async def cleanup_expired(self):
        """清理过期的重连令牌和恢复数据"""
        async with self._lock:
            now = time.time()

            # 清理过期的重连令牌
            expired_tokens = [
                token
                for token, data in self._reconnect_tokens.items()
                if now > data["expiry"]
            ]
            for token in expired_tokens:
                del self._reconnect_tokens[token]

            # 清理过期的恢复数据
            expired_sessions = [
                sid
                for sid, data in self._session_recovery_data.items()
                if now > data["expiry"]
            ]
            for sid in expired_sessions:
                del self._session_recovery_data[sid]


# 全局重连管理器
reconnect_manager = ReconnectManager()


# ==================== 发送队列（支持压缩）====================
class SafeWebSocketSender:
    """安全的WebSocket发送器（带队列和压缩）"""

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        max_queue_size: int = WS_SEND_QUEUE_SIZE,
        enable_compression: bool = True,
    ):
        self.websocket = websocket
        self.session_id = session_id
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.task: Optional[asyncio.Task] = None
        self.closed = False
        self.dropped_count = 0
        self.enable_compression = enable_compression
        self.compression_level = COMPRESSION_LEVEL

        # 统计
        self.compressed_frames = 0
        self.uncompressed_frames = 0
        self.compressed_bytes_saved = 0

    async def send_bytes(self, data: bytes) -> bool:
        """直接发送二进制数据"""
        if self.closed:
            return False

        try:
            await asyncio.wait_for(
                self.websocket.send_bytes(data), timeout=WS_SEND_TIMEOUT
            )
            return True
        except asyncio.TimeoutError:
            logger.debug(f"会话 {self.session_id} 发送超时")
        except Exception as e:
            logger.debug(f"会话 {self.session_id} 发送失败: {e}")
        return False

    async def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._send_loop())

    async def stop(self):
        self.closed = True
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def send(self, message: Dict) -> bool:
        if self.closed:
            return False

        # 对帧数据进行压缩
        if self.enable_compression and message.get("type") == "frame":
            compressed_msg = await self._compress_frame(message)
            if compressed_msg:
                message = compressed_msg

        try:
            await asyncio.wait_for(self.queue.put(message), timeout=1.0)
            return True
        except asyncio.TimeoutError:
            self.dropped_count += 1
            if self.dropped_count % 10 == 1:
                logger.warning(
                    f"会话 {self.session_id} 发送队列已满，已丢弃 {self.dropped_count} 条消息"
                )
            return False

    async def _compress_frame(self, message: Dict) -> Optional[Dict]:
        """压缩帧数据 - 避免重复压缩"""
        try:
            # ✅ 如果已经压缩过，直接返回
            if message.get("compressed") is True:
                self.uncompressed_frames += 1
                return None

            frame_data = message.get("data", "")
            if not frame_data or len(frame_data) < COMPRESSION_MIN_SIZE:
                self.uncompressed_frames += 1
                return None

            original_size = len(frame_data)
            compressed_data, compressed = FrameCompressor.compress(
                frame_data, self.compression_level
            )

            if compressed:
                encoded_data = base64.b64encode(compressed_data).decode("ascii")
                message["data"] = encoded_data
                message["compressed"] = True
                message["original_size"] = original_size
                message["compressed_size"] = len(compressed_data)

                self.compressed_frames += 1
                self.compressed_bytes_saved += original_size - len(compressed_data)

                logger.debug(
                    f"帧压缩: {original_size} -> {len(compressed_data)} bytes (节省 {100 - len(compressed_data)*100/original_size:.1f}%)"
                )
                return message
            else:
                self.uncompressed_frames += 1
                return message

        except Exception as e:
            logger.error(f"压缩帧失败: {e}")
            self.uncompressed_frames += 1
            return message

    async def _send_loop(self):
        """发送循环 - 负责从队列中提取消息并发送"""
        while not self.closed:
            try:
                # 从队列中获取待发送的消息
                message = await self.queue.get()

                # ✅ 确保 message 是字典，如果是字符串则尝试转换，确保后续处理一致性
                if isinstance(message, str):
                    try:
                        message = json.loads(message)
                    except Exception:
                        # 如果转换失败（说明本身就是非 JSON 字符串），直接发送原样字符串
                        json_str = message
                        await self.websocket.send_text(json_str)
                        self.queue.task_done()
                        continue

                # ✅ 此时 message 确定为字典，统一序列化为 JSON 字符串
                # 使用 ensure_ascii=False 以便在日志和传输中直接显示中文字符
                json_str = json.dumps(message, ensure_ascii=False)

                msg_type = message.get("type", "unknown")
                # 生产环境建议对大的 payload（如图像数据）进行日志截断

                try:
                    # 使用 wait_for 防止因网络拥塞导致发送协程永久挂起
                    await asyncio.wait_for(
                        self.websocket.send_text(json_str), timeout=WS_SEND_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.debug(f"会话 {self.session_id} 发送超时 (type: {msg_type})")
                except Exception as e:
                    logger.debug(f"会话 {self.session_id} 发送失败: {e}")
                finally:
                    # 标记任务完成
                    self.queue.task_done()

            except asyncio.CancelledError:
                # 协程被取消（如连接关闭），优雅退出循环
                break
            except Exception as e:
                logger.debug(f"会话 {self.session_id} 发送循环异常: {e}")


# ==================== 工具函数（增强版）====================
def safe_json_loads(data: str) -> Optional[Dict]:
    """安全解析JSON（支持压缩数据）"""
    if not isinstance(data, str):
        return None
    try:
        if len(data) > WS_MAX_MESSAGE_SIZE:
            logger.warning(f"JSON消息过大: {len(data)} bytes")
            return None
        return json.loads(data)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON解析失败: {e}")
        return None


def safe_json_dumps(data: Dict) -> Optional[str]:
    """安全生成JSON"""
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"JSON生成失败: {e}")
        return None


async def decompress_frame_data(data: Dict) -> Dict:
    """解压帧数据"""
    if data.get("type") != "frame":
        return data

    if data.get("compressed"):
        try:
            compressed_data = base64.b64decode(data["data"])
            decompressed_data = FrameCompressor.decompress(compressed_data)
            data["data"] = decompressed_data
            data.pop("compressed", None)
            data.pop("original_size", None)
            data.pop("compressed_size", None)
            logger.debug("帧数据解压成功")
        except Exception as e:
            logger.error(f"解压帧数据失败: {e}")

    return data


def validate_and_sanitize_employee_id(employee_id: str) -> Optional[str]:
    """验证并清理员工ID（支持域用户格式和中文）"""
    if not employee_id or len(employee_id) > 100:
        return None
    # 允许字母、数字、下划线、横线、反斜杠、点、空格、括号、@（域用户格式：DOMAIN\username）
    # 同时支持中文用户名
    if not re.match(r"^[a-zA-Z0-9_\-\\\u4e00-\u9fff\s.@()]+$", employee_id):
        return None
    return employee_id.strip()


def validate_client_id(client_id: str) -> Optional[str]:
    """验证并清理客户端ID"""
    if not client_id or len(client_id) > 100:
        return None
    if not re.match(r"^[a-zA-Z0-9_\-]+$", client_id):
        return None
    return client_id


def validate_frame_data(data: Dict) -> Tuple[bool, Optional[str]]:
    """验证帧数据"""
    if "type" not in data or data["type"] != "frame":
        return False, "消息类型不是frame"

    frame_data = data.get("data", "")
    if not frame_data:
        return False, "帧数据为空"

    # 如果是压缩数据，按压缩后的大小验证
    if data.get("compressed"):
        compressed_size = len(frame_data) if isinstance(frame_data, str) else 0
        if compressed_size > WS_MAX_FRAME_SIZE:
            return False, f"压缩帧数据过大: {compressed_size} bytes"
    else:
        if isinstance(frame_data, str) and len(frame_data) > WS_MAX_FRAME_SIZE:
            return False, f"帧数据过大: {len(frame_data)} bytes"

    return True, None


def validate_config_update(config: Dict) -> Dict:
    validated = {}
    for key, value in config.items():
        if key in ALLOWED_CONFIG_FIELDS:
            field_def = ALLOWED_CONFIG_FIELDS[key]
            if isinstance(field_def, tuple):
                expected_type, min_val, max_val = field_def
                if isinstance(value, expected_type) and min_val <= value <= max_val:
                    validated[key] = value
            elif field_def == bool:
                # 处理 bool 类型，支持字符串转换
                if isinstance(value, bool):
                    validated[key] = value
                elif isinstance(value, str):
                    if value.lower() in ("true", "1", "yes", "on"):
                        validated[key] = True
                    elif value.lower() in ("false", "0", "no", "off"):
                        validated[key] = False
            elif isinstance(value, field_def):
                validated[key] = value
    return validated


async def verify_websocket_token(
    token: str, expected_role: str = None
) -> Optional[Dict]:
    """验证WebSocket令牌"""
    if not token:
        return None

    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=[Config.ALGORITHM])

        if expected_role and payload.get("role") != expected_role:
            logger.warning(
                f"角色不匹配: 需要 {expected_role}, 实际 {payload.get('role')}"
            )
            return None

        return payload
    except ExpiredSignatureError:
        logger.warning("令牌已过期")
        return None
    except JWTError as e:
        logger.warning(f"令牌验证失败: {e}")
        return None


async def safe_websocket_send(websocket: WebSocket, message: Dict) -> bool:
    """安全的WebSocket发送 - 确保 JSON 格式"""
    if not websocket:
        return False

    try:
        if websocket.client_state != WebSocketState.CONNECTED:
            return False
    except Exception:
        return False

    # ✅ 确保使用 json.dumps 转换为 JSON 字符串
    try:
        json_str = json.dumps(message, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"JSON生成失败: {e}")
        return False

    try:
        await asyncio.wait_for(websocket.send_text(json_str), timeout=WS_SEND_TIMEOUT)
        return True
    except asyncio.TimeoutError:
        logger.debug("WebSocket发送超时")
    except Exception as e:
        logger.debug(f"WebSocket发送失败: {e}")
    return False


# ==================== 会话管理器（企业增强版）====================
class RemoteSessionManager:
    """专业级远程屏幕会话管理器（企业增强版）"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 活跃会话 {session_id: session_info}
        self.active_sessions: Dict[str, Dict] = {}

        # 员工到会话的映射 {employee_id: session_id}
        self.employee_to_session: Dict[str, str] = {}

        # 客户端到管理端的映射 {client_id: set(session_ids)}
        self.client_to_admin: Dict[str, Set[str]] = defaultdict(set)

        # 管理员到会话的映射 {admin_user: set(session_ids)}
        self.admin_to_sessions: Dict[str, Set[str]] = defaultdict(set)

        self.client_websockets: Dict[str, WebSocket] = {}
        self._client_ws_lock = asyncio.Lock()

        # 会话统计
        self.session_stats: Dict[str, Dict] = {}
        self.MAX_STATS_AGE = 86400  # 24小时

        # 帧统计缓冲
        self._frame_stats_buffer: Dict[str, Tuple[int, int]] = {}
        self._last_frame_stats_update: Dict[str, float] = {}

        # 统计更新节流
        self._last_stats_update: Dict[str, float] = {}

        # 锁
        self._lock = asyncio.Lock()

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None

        # 广播任务跟踪
        self._broadcast_tasks: Set[asyncio.Task] = set()

        self.logger.info("✅ 远程屏幕会话管理器已初始化（企业增强版）")

    async def register_client_websocket(self, client_id: str, websocket: WebSocket):
        """注册客户端WebSocket连接"""
        async with self._client_ws_lock:
            self.client_websockets[client_id] = websocket
            self.logger.info(f"✅ 客户端WebSocket已注册: {client_id}")

    async def unregister_client_websocket(self, client_id: str):
        """注销客户端WebSocket连接"""
        async with self._client_ws_lock:
            if client_id in self.client_websockets:
                del self.client_websockets[client_id]
                self.logger.info(f"✅ 客户端WebSocket已注销: {client_id}")

    async def get_client_websocket(self, client_id: str) -> Optional[WebSocket]:
        """获取客户端的 WebSocket 连接，并检查其活跃状态"""
        async with self._client_ws_lock:
            ws = self.client_websockets.get(client_id)
            if ws:
                try:
                    # ✅ 核心逻辑：检查连接是否处于 CONNECTED 状态
                    # 这能有效防止 broadcast_to_client 向已经失效的连接发送数据
                    if ws.client_state == WebSocketState.CONNECTED:
                        return ws
                    else:
                        # 连接已失效（可能由于网络波动或非正常关闭），执行清理
                        self.logger.warning(
                            f"⚠️ 客户端 {client_id} WebSocket 已失效，正在从连接池移除"
                        )
                        if client_id in self.client_websockets:
                            del self.client_websockets[client_id]
                except Exception as e:
                    self.logger.error(
                        f"❌ 检查客户端 {client_id} 连接状态失败: {e}", exc_info=True
                    )
                    # 状态检查抛出异常，通常意味着该对象已不可用
                    if client_id in self.client_websockets:
                        del self.client_websockets[client_id]

            return None

    async def start_cleanup_task(self):
        """启动清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self.logger.info("✅ 清理任务已启动")

    async def stop_cleanup_task(self):
        """停止清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_broadcast_tasks(self):
        """清理已完成的广播任务"""
        if self._broadcast_tasks:
            done_tasks = {t for t in self._broadcast_tasks if t.done()}
            for task in done_tasks:
                self._broadcast_tasks.discard(task)
                try:
                    task.result()
                except Exception as e:
                    logger.debug(f"广播任务异常: {e}")

    async def create_session(
        self,
        websocket: WebSocket,
        employee_id: str,
        client_id: str,
        admin_user: str,
        admin_id: int,
        enable_compression: bool = True,
    ) -> str:
        """创建新会话"""
        async with self._lock:
            session_id = f"remote_{int(time.time())}_{employee_id[:8]}_{admin_user[:8]}"

            sender = SafeWebSocketSender(
                websocket, session_id, enable_compression=enable_compression
            )
            await sender.start()

            self.active_sessions[session_id] = {
                "session_id": session_id,
                "websocket": websocket,
                "sender": sender,
                "employee_id": employee_id,
                "client_id": client_id,
                "admin_user": admin_user,
                "admin_id": admin_id,
                "start_time": time.time(),
                "last_heartbeat": time.time(),
                "last_frame_time": 0,
                "last_viewer_update": 0,
                "status": "active",
                "quality": 80,
                "fps": 5,
                "width": 1280,
                "height": 720,
                "network_quality": 100,
                "enable_compression": enable_compression,
                "config": {
                    "enable_diff": True,
                    "enable_region": True,
                    "enable_h264": True,
                    "enable_qr": False,
                    "enable_compression": enable_compression,
                },
            }

            self.employee_to_session[employee_id] = session_id
            self.client_to_admin[client_id].add(session_id)
            self.logger.info(
                f"✅ 添加映射: client_id={client_id} -> session_id={session_id}"
            )
            self.logger.info(
                f"   当前客户端 {client_id} 的会话数: {len(self.client_to_admin[client_id])}"
            )
            self.logger.info(f"   所有会话: {dict(self.client_to_admin)}")
            self.admin_to_sessions[admin_user].add(session_id)

            self.session_stats[session_id] = {
                "frames_sent": 0,
                "bytes_sent": 0,
                "start_time": time.time(),
                "last_activity": time.time(),
                "end_time": None,
                "qr_detected": 0,
                "commands_sent": 0,
                "errors": 0,
                "duration": 0,
                "compressed_frames": 0,
                "compressed_bytes_saved": 0,
            }

            self._frame_stats_buffer[session_id] = (0, 0)
            self._last_frame_stats_update[session_id] = time.time()
            self._last_stats_update[session_id] = time.time()

            self.logger.info(
                f"✅ 远程会话创建: {session_id} (压缩: {'启用' if enable_compression else '禁用'})"
            )
            return session_id

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话（不包含WebSocket对象）"""
        async with self._lock:
            if session_id not in self.active_sessions:
                return None
            session = self.active_sessions[session_id].copy()
            session.pop("websocket", None)
            session.pop("sender", None)
            return session

    async def get_session_by_employee(self, employee_id: str) -> Optional[Dict]:
        """通过员工ID获取会话"""
        async with self._lock:
            session_id = self.employee_to_session.get(employee_id)
            if session_id and session_id in self.active_sessions:
                session = self.active_sessions[session_id].copy()
                session.pop("websocket", None)
                session.pop("sender", None)
                return session
            return None

    async def get_sessions_by_client(self, client_id: str) -> List[Dict]:
        """通过客户端ID获取所有会话"""
        async with self._lock:
            session_ids = self.client_to_admin.get(client_id, set())
            sessions = []
            for sid in session_ids:
                if sid in self.active_sessions:
                    session_info = self.active_sessions[sid].copy()
                    session_info.pop("websocket", None)
                    session_info.pop("sender", None)
                    sessions.append(session_info)
            return sessions

    async def get_sessions_by_admin(self, admin_user: str) -> List[Dict]:
        """通过管理员获取所有会话"""
        async with self._lock:
            session_ids = self.admin_to_sessions.get(admin_user, set())
            sessions = []
            for sid in session_ids:
                if sid in self.active_sessions:
                    session_info = self.active_sessions[sid].copy()
                    session_info.pop("websocket", None)
                    session_info.pop("sender", None)
                    sessions.append(session_info)
            return sessions

    async def get_websockets_by_client(
        self, client_id: str
    ) -> List[Tuple[str, SafeWebSocketSender]]:
        """获取客户端的所有WebSocket发送器"""
        async with self._lock:
            session_ids = self.client_to_admin.get(client_id, set())
            result = []
            for sid in session_ids:
                if sid in self.active_sessions:
                    session = self.active_sessions[sid]
                    sender = session.get("sender")
                    ws = session.get("websocket")
                    if sender and ws:
                        try:
                            if ws.client_state == WebSocketState.CONNECTED:
                                result.append((sid, sender))
                        except Exception:
                            pass
            return result

    async def send_to_session(self, session_id: str, message: Dict) -> bool:
        """向指定会话发送消息"""
        async with self._lock:
            session = self.active_sessions.get(session_id)
            if not session:
                return False
            sender = session.get("sender")
            if not sender:
                return False
        return await sender.send(message)

    async def close_session(
        self, session_id: str, reason: str = "正常关闭", store_recovery: bool = False
    ):
        """关闭会话（支持存储恢复数据）"""
        websocket_to_close = None
        client_id = None
        admin_user = None
        employee_id = None
        session_data = None

        async with self._lock:
            if session_id not in self.active_sessions:
                return

            session = self.active_sessions[session_id]
            employee_id = session["employee_id"]
            client_id = session["client_id"]
            admin_user = session["admin_user"]
            websocket_to_close = session.get("websocket")

            # 存储恢复数据（如果需要）
            if store_recovery:
                session_data = {
                    "employee_id": employee_id,
                    "client_id": client_id,
                    "admin_user": admin_user,
                    "admin_id": session["admin_id"],
                    "quality": session.get("quality", 80),
                    "fps": session.get("fps", 5),
                    "config": session.get("config", {}),
                    "enable_compression": session.get("enable_compression", True),
                }

            sender = session.get("sender")
            if sender:
                # 更新压缩统计
                if session_id in self.session_stats:
                    self.session_stats[session_id][
                        "compressed_frames"
                    ] = sender.compressed_frames
                    self.session_stats[session_id][
                        "compressed_bytes_saved"
                    ] = sender.compressed_bytes_saved
                await sender.stop()

            # 清理映射
            if employee_id in self.employee_to_session:
                del self.employee_to_session[employee_id]

            if client_id in self.client_to_admin:
                self.client_to_admin[client_id].discard(session_id)
                if not self.client_to_admin[client_id]:
                    del self.client_to_admin[client_id]

            if admin_user in self.admin_to_sessions:
                self.admin_to_sessions[admin_user].discard(session_id)
                if not self.admin_to_sessions[admin_user]:
                    del self.admin_to_sessions[admin_user]

            # 删除会话
            del self.active_sessions[session_id]

            # 清理缓冲
            self._frame_stats_buffer.pop(session_id, None)
            self._last_frame_stats_update.pop(session_id, None)
            self._last_stats_update.pop(session_id, None)

            # 更新统计
            if session_id in self.session_stats:
                self.session_stats[session_id]["end_time"] = time.time()
                self.session_stats[session_id]["duration"] = (
                    time.time() - self.session_stats[session_id]["start_time"]
                )

            self.logger.info(f"🔚 会话关闭: {session_id} (原因: {reason})")

        # 存储恢复数据
        if store_recovery and session_data:
            await reconnect_manager.store_recovery_data(session_id, session_data)
            # 生成重连令牌
            reconnect_token = reconnect_manager.generate_reconnect_token(
                session_id, employee_id, client_id, admin_user
            )
            # 尝试发送重连令牌给客户端
            if websocket_to_close:
                try:
                    await safe_websocket_send(
                        websocket_to_close,
                        {
                            "type": "reconnect_token",
                            "token": reconnect_token,
                            "session_id": session_id,
                            "expiry": RECONNECT_TOKEN_EXPIRY,
                            "timestamp": time.time(),
                        },
                    )
                except Exception:
                    pass

        # 在锁外关闭WebSocket
        if websocket_to_close:
            try:
                if websocket_to_close.client_state != WebSocketState.DISCONNECTED:
                    asyncio.create_task(
                        websocket_to_close.close(code=1000, reason=reason)
                    )
            except Exception as e:
                logger.debug(f"关闭WebSocket失败: {e}")

        # 广播观众更新
        if client_id:
            await self.broadcast_viewer_update(client_id, force=True)

    async def recover_session(
        self, session_id: str, websocket: WebSocket, reconnect_token: str
    ) -> Optional[str]:
        """恢复会话"""
        # 验证重连令牌
        token_data = await reconnect_manager.validate_reconnect_token(reconnect_token)
        if not token_data or token_data["session_id"] != session_id:
            logger.warning(f"无效的重连令牌: {session_id}")
            return None

        # 获取恢复数据
        recovery_data = await reconnect_manager.get_recovery_data(session_id)
        if not recovery_data:
            logger.warning(f"无恢复数据: {session_id}")
            return None

        # 创建新会话（使用恢复的数据）
        new_session_id = await self.create_session(
            websocket,
            recovery_data["employee_id"],
            recovery_data["client_id"],
            recovery_data["admin_user"],
            recovery_data["admin_id"],
            recovery_data.get("enable_compression", True),
        )

        # 恢复配置
        if new_session_id:
            async with self._lock:
                if new_session_id in self.active_sessions:
                    self.active_sessions[new_session_id]["quality"] = recovery_data.get(
                        "quality", 80
                    )
                    self.active_sessions[new_session_id]["fps"] = recovery_data.get(
                        "fps", 5
                    )
                    self.active_sessions[new_session_id]["config"] = recovery_data.get(
                        "config", {}
                    )

            logger.info(f"✅ 会话恢复成功: {session_id} -> {new_session_id}")

            # 清理旧数据
            await reconnect_manager.clear_recovery_data(session_id)

            return new_session_id

        return None

    async def close_all_sessions_for_client(
        self, client_id: str, reason: str = "客户端断开"
    ):
        """关闭客户端的所有会话"""
        session_ids = []
        async with self._lock:
            session_ids = list(self.client_to_admin.get(client_id, set()))

        close_tasks = []
        for session_id in session_ids:
            close_tasks.append(self.close_session(session_id, reason))

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        if session_ids:
            self.logger.info(
                f"🔚 客户端 {client_id} 的 {len(session_ids)} 个会话已关闭"
            )

    async def update_session_stats(self, session_id: str, **kwargs):
        """更新会话统计（带节流）"""
        if not session_id:
            return

        now = time.time()

        # 帧计数和字节计数节流
        if "frames_sent" in kwargs or "bytes_sent" in kwargs:
            last_update = self._last_stats_update.get(session_id, 0)
            if now - last_update < FRAME_STATS_INTERVAL:
                # 累积更新
                async with self._lock:
                    if session_id in self.session_stats:
                        if "frames_sent" in kwargs:
                            self.session_stats[session_id]["frames_sent"] += kwargs[
                                "frames_sent"
                            ]
                        if "bytes_sent" in kwargs:
                            self.session_stats[session_id]["bytes_sent"] += kwargs[
                                "bytes_sent"
                            ]
                        if "qr_detected" in kwargs:
                            self.session_stats[session_id]["qr_detected"] += kwargs[
                                "qr_detected"
                            ]
                        if "commands_sent" in kwargs:
                            self.session_stats[session_id]["commands_sent"] += kwargs[
                                "commands_sent"
                            ]
                return
            self._last_stats_update[session_id] = now

        async with self._lock:
            if session_id in self.active_sessions:
                # 更新会话属性
                for key, value in kwargs.items():
                    if key in ["last_heartbeat", "quality", "fps", "network_quality"]:
                        self.active_sessions[session_id][key] = value

                # 更新统计
                if session_id in self.session_stats:
                    self.session_stats[session_id]["last_activity"] = now
                    if "frames_sent" in kwargs:
                        self.session_stats[session_id]["frames_sent"] += kwargs[
                            "frames_sent"
                        ]
                    if "bytes_sent" in kwargs:
                        self.session_stats[session_id]["bytes_sent"] += kwargs[
                            "bytes_sent"
                        ]
                    if "qr_detected" in kwargs:
                        self.session_stats[session_id]["qr_detected"] += kwargs[
                            "qr_detected"
                        ]
                    if "commands_sent" in kwargs:
                        self.session_stats[session_id]["commands_sent"] += kwargs[
                            "commands_sent"
                        ]
                    if "errors" in kwargs:
                        self.session_stats[session_id]["errors"] += kwargs["errors"]

    async def update_frame_stats(self, session_id: str, frame_size: int):
        """批量更新帧统计"""
        now = time.time()

        async with self._lock:
            if session_id in self._frame_stats_buffer:
                frames, bytes_sent = self._frame_stats_buffer[session_id]
                self._frame_stats_buffer[session_id] = (
                    frames + 1,
                    bytes_sent + frame_size,
                )

                last_update = self._last_frame_stats_update.get(session_id, now)
                if (
                    frames + 1 >= FRAME_STATS_BATCH
                    or now - last_update > FRAME_STATS_INTERVAL
                ):
                    if session_id in self.session_stats:
                        stats = self.session_stats[session_id]
                        stats["frames_sent"] += frames + 1
                        stats["bytes_sent"] += bytes_sent + frame_size
                        stats["last_activity"] = now

                    self._frame_stats_buffer[session_id] = (0, 0)
                    self._last_frame_stats_update[session_id] = now

                    if session_id in self.active_sessions:
                        self.active_sessions[session_id]["last_frame_time"] = now

    async def update_client_compression_config(
        self, client_id: str, enable_compression: bool, broadcast: bool = True
    ):
        """更新客户端所有会话的压缩配置，并可选择广播通知"""
        sessions = await self.get_sessions_by_client(client_id)

        if not sessions:
            return

        update_tasks = []
        for session in sessions:
            session_id = session.get("session_id")
            if session_id:
                update_tasks.append(
                    self.update_session_compression(session_id, enable_compression)
                )

        if update_tasks:
            await asyncio.gather(*update_tasks, return_exceptions=True)

            # 广播通知所有管理员
            if broadcast:
                broadcast_tasks = []
                for session in sessions:
                    session_id = session.get("session_id")
                    if session_id:
                        broadcast_tasks.append(
                            self.broadcast_compression_update(
                                client_id, session_id, enable_compression
                            )
                        )
                if broadcast_tasks:
                    await asyncio.gather(*broadcast_tasks, return_exceptions=True)

            logger.info(
                f"✅ 客户端 {client_id} 的 {len(update_tasks)} 个会话压缩配置已更新"
            )

    async def broadcast_to_client(self, client_id: str, message: dict) -> int:
        """向客户端的所有会话广播消息"""
        success_count = 0

        # ✅ 1. 先尝试通过管理员会话发送（如果有管理员在查看该员工）
        items = await self.get_websockets_by_client(client_id)

      

        if items:
            tasks = []
            for sid, sender in items:
                # sender.send 通常是自定义封装类，接受字典并在内部序列化
                task = asyncio.create_task(sender.send(message))
                tasks.append(task)
                self._broadcast_tasks.add(task)
                task.add_done_callback(self._broadcast_tasks.discard)

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # sender.send 返回 True 表示发送成功
                success_count = sum(1 for r in results if r is True)

        # ✅ 2. 直接通过客户端原始 WebSocket 发送
        client_ws = await self.get_client_websocket(client_id)
        if client_ws:
            try:
                # ✅ 关键点：使用 FastAPI 提供的 send_json 方法
                # 它会自动处理 json.dumps 并以正确的文本帧格式发送，避免类型报错
                await client_ws.send_json(message)
                success_count += 1
            except Exception as e:
                self.logger.error(
                    f"📢 直接发送到客户端 {client_id} 失败: {e}", exc_info=True
                )

       

        return success_count

    async def broadcast_viewer_update(self, client_id: str, force: bool = False):
        """广播观众数量更新（带冷却）"""
        now = time.time()
        viewer_count = 0  # ✅ 在锁外定义变量

        async with self._lock:
            sessions = self.client_to_admin.get(client_id, set())
            viewer_count = len(sessions)

      
            if not sessions:
                return

            if not force:
                need_update = False
                for sid in sessions:
                    if sid in self.active_sessions:
                        last = self.active_sessions[sid].get("last_viewer_update", 0)
                        if now - last >= VIEWER_UPDATE_COOLDOWN:
                            need_update = True
                            break
                if not need_update:
                    self.logger.info(f"   ⏸️ 冷却中，跳过广播")
                    return

            # 更新时间戳
            for sid in sessions:
                if sid in self.active_sessions:
                    self.active_sessions[sid]["last_viewer_update"] = now

        # ✅ 现在 viewer_count 肯定有值
        result = await self.broadcast_to_client(
            client_id,
            {
                "type": "viewer_update",
                "viewers": viewer_count,
                "timestamp": now,
            },
        )

    async def get_viewer_count(self, client_id: str) -> int:
        """获取客户端的观众数量"""
        async with self._lock:
            return len(self.client_to_admin.get(client_id, set()))

    async def forward_frame_to_admins(
        self, client_id: str, message: str, frame_size: int
    ):
        """低延迟转发 - 支持 WebP 和 JPEG，支持新协议"""
        try:
            data = json.loads(message)
            if data.get("type") != "frame":
                return
        except Exception as e:
            self.logger.error(f"❌ 解析消息失败: {e}")
            return

        items = await self.get_websockets_by_client(client_id)
        if not items:
            self.logger.warning("⚠️ 没有管理员会话，丢弃帧")
            return

        try:
            encoded_data = data.get("data")
            if not encoded_data:
                self.logger.error("❌ 缺少 data 字段")
                return

            image_data = base64.b64decode(encoded_data)
            img_format = data.get("format", "jpeg")

            # ✅ 验证格式
            if img_format == "webp":
                if len(image_data) >= 4 and image_data[0:4] == b"RIFF":
                    self.logger.dgbug(f"✅ WebP 格式验证通过，大小={len(image_data)}")
                else:
                    self.logger.dgbug(f"❌ WebP 头无效: {image_data[:4].hex()}")
                    return
            elif img_format == "jpeg":
                if (
                    len(image_data) >= 2
                    and image_data[0] == 0xFF
                    and image_data[1] == 0xD8
                ):
                    self.logger.dgbug(f"✅ JPEG 格式验证通过，大小={len(image_data)}")
                else:
                    self.logger.error(f"❌ JPEG 头无效: {image_data[:2].hex()}")
                    return

            width = int(data.get("width", 1280))
            height = int(data.get("height", 720))

            # ✅ 获取帧ID和时间戳（如果有）
            frame_id = data.get("frame_id", 0)
            timestamp_ms = data.get("timestamp_ms", int(time.time() * 1000))

            # ✅ 构建20字节帧头（新协议）
            header = bytearray(20)
            header[0] = 2  # 版本号2（新协议）
            header[1] = self._get_frame_type_code(data)
            header[2:4] = width.to_bytes(2, "big")
            header[4:6] = height.to_bytes(2, "big")
            header[6:8] = (0).to_bytes(2, "big")  # 保留
            header[8:12] = frame_id.to_bytes(4, "big")
            header[12:16] = timestamp_ms.to_bytes(4, "big")
            header[16:20] = len(image_data).to_bytes(4, "big")

            binary_frame = bytes(header) + image_data

            # 转发
            for sid, sender in items:
                try:
                    if hasattr(sender, "send_bytes"):
                        await sender.send_bytes(binary_frame)
                    elif hasattr(sender, "websocket") and hasattr(
                        sender.websocket, "send_bytes"
                    ):
                        await sender.websocket.send_bytes(binary_frame)
                    else:
                        await sender.send(
                            json.dumps(
                                {
                                    "type": "frame",
                                    "data": encoded_data,
                                    "width": width,
                                    "height": height,
                                    "format": img_format,
                                    "frame_id": frame_id,
                                    "timestamp_ms": timestamp_ms,
                                }
                            )
                        )

                    asyncio.create_task(self.update_frame_stats(sid, len(image_data)))

                except Exception as e:
                    self.logger.error(f"❌ 发送失败 sid={sid}: {e}")

          

        except Exception as e:
            self.logger.error(f"❌ 转发失败: {e}", exc_info=True)

    def _get_frame_type_code(self, data: dict) -> int:
        """获取帧类型编码"""
        frame_type = data.get("frame_type", "full_frame")
        codes = {
            "full_frame": 1,
            "diff_frame": 2,
            "region_frame": 3,
        }
        return codes.get(frame_type, 1)

    async def _cleanup_loop(self):
        """清理过期会话"""
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)
                await self._cleanup_broadcast_tasks()
                await reconnect_manager.cleanup_expired()

                now = time.time()
                to_close = []
                to_remove_stats = []

                async with self._lock:
                    for session_id, session in list(self.active_sessions.items()):
                        if now - session["last_heartbeat"] > HEARTBEAT_TIMEOUT:
                            to_close.append((session_id, "心跳超时"))
                            continue

                        if now - session["start_time"] > MAX_SESSION_AGE:
                            to_close.append((session_id, "会话超时"))
                            continue

                        ws = session.get("websocket")
                        if not ws:
                            to_close.append((session_id, "WebSocket对象不存在"))
                            continue

                        try:
                            if ws.client_state != WebSocketState.CONNECTED:
                                to_close.append((session_id, "连接已断开"))
                        except Exception:
                            to_close.append((session_id, "连接状态检查失败"))

                    # 清理过期统计
                    for session_id, stats in list(self.session_stats.items()):
                        if (
                            stats.get("end_time")
                            and now - stats["end_time"] > self.MAX_STATS_AGE
                        ):
                            to_remove_stats.append(session_id)
                        elif (
                            session_id not in self.active_sessions
                            and now - stats["last_activity"] > self.MAX_STATS_AGE
                        ):
                            to_remove_stats.append(session_id)

                    for session_id in to_remove_stats:
                        self.session_stats.pop(session_id, None)

                for session_id, reason in to_close:
                    await self.close_session(session_id, reason, store_recovery=True)

                if to_close:
                    self.logger.info(f"🧹 清理完成: 关闭 {len(to_close)} 个会话")

            except asyncio.CancelledError:
                self.logger.info("清理任务被取消")
                break
            except Exception as e:
                self.logger.error(f"清理会话异常: {e}")


# 全局会话管理器
session_manager = RemoteSessionManager()


async def start_remote_service():
    """启动远程屏幕服务"""
    await session_manager.start_cleanup_task()
    logger.info("✅ 远程屏幕服务已启动")


async def shutdown_remote_service():
    """关闭远程屏幕服务"""
    # 等待所有广播任务完成
    if session_manager._broadcast_tasks:
        remaining = [t for t in session_manager._broadcast_tasks if not t.done()]
        if remaining:
            logger.info(f"⏳ 等待 {len(remaining)} 个广播任务完成...")
            await asyncio.gather(*remaining, return_exceptions=True)

    await session_manager.stop_cleanup_task()
    logger.info("✅ 远程屏幕服务已关闭")


# ==================== 辅助函数 ====================
async def _broadcast_viewer_update(client_id: str):
    """广播观众更新（辅助函数）"""
    try:
        await session_manager.broadcast_viewer_update(client_id, force=True)
    except Exception as e:
        logger.error(f"❌ 广播观众更新失败: {e}")


# ==================== 健康检查 ====================
@router.get("/health")
async def remote_health_check():
    """远程屏幕服务健康检查"""
    total_frames = sum(
        s.get("frames_sent", 0) for s in session_manager.session_stats.values()
    )
    total_bytes = sum(
        s.get("bytes_sent", 0) for s in session_manager.session_stats.values()
    )
    total_compressed_frames = sum(
        s.get("compressed_frames", 0) for s in session_manager.session_stats.values()
    )
    total_compressed_saved = sum(
        s.get("compressed_bytes_saved", 0)
        for s in session_manager.session_stats.values()
    )

    return {
        "status": "healthy",
        "active_sessions": len(session_manager.active_sessions),
        "active_clients": len(session_manager.client_to_admin),
        "active_admins": len(session_manager.admin_to_sessions),
        "total_frames": total_frames,
        "total_bytes": total_bytes,
        "total_bytes_mb": round(total_bytes / (1024 * 1024), 2),
        "compression_stats": {
            "enabled": COMPRESSION_ENABLED,
            "compressed_frames": total_compressed_frames,
            "bytes_saved": total_compressed_saved,
            "bytes_saved_mb": round(total_compressed_saved / (1024 * 1024), 2),
        },
        "timestamp": datetime.now().isoformat(),
    }


# ==================== 管理端WebSocket（支持断线重连）====================
async def _handle_admin_messages(
    websocket: WebSocket,
    session_id: str,
    client_id: str,
    admin_username: str,
) -> None:
    """处理管理员会话的消息循环"""
    last_heartbeat = time.time()

    while True:
        try:
            message = await asyncio.wait_for(
                websocket.receive_text(), timeout=WS_HEARTBEAT_INTERVAL
            )
        except asyncio.TimeoutError:
            if time.time() - last_heartbeat > WS_IDLE_TIMEOUT:
                logger.info(f"⏰ 空闲超时，关闭会话: {session_id}")
                break
            continue

        if len(message) > WS_MAX_MESSAGE_SIZE:
            logger.warning(f"消息过大: {len(message)} bytes")
            continue

        data = safe_json_loads(message)
        if not data:
            continue

        msg_type = data.get("type")

        if msg_type == "frame":
            # 管理员不应该发送帧数据
            logger.warning(f"⚠️ 管理员尝试发送帧数据，已忽略 (session: {session_id})")
            continue

        elif msg_type == "heartbeat":
            last_heartbeat = time.time()
            await session_manager.update_session_stats(
                session_id, last_heartbeat=last_heartbeat
            )
            await session_manager.send_to_session(
                session_id, {"type": "heartbeat_ack", "timestamp": time.time()}
            )

        elif msg_type == "command":
            command = data.get("command")
            target = data.get("target", "client")
            params = data.get("params", {})

            logger.info(f"📋 收到命令: {command}, 目标: {target}")

            if target == "client" and client_id:
                await session_manager.broadcast_to_client(
                    client_id,
                    {
                        "type": "command",
                        "command": command,
                        "params": params,
                        "session_id": session_id,
                        "admin": admin_username,
                        "timestamp": time.time(),
                    },
                )
                await session_manager.update_session_stats(session_id, commands_sent=1)

        elif msg_type == "ping":
            await session_manager.send_to_session(
                session_id,
                {
                    "type": "pong",
                    "timestamp": data.get("timestamp", time.time()),
                },
            )

        elif msg_type == "config_change":
            new_config = validate_config_update(data.get("config", {}))
            if new_config and client_id:
                # 更新压缩配置
                if "enable_compression" in new_config:
                    async with session_manager._lock:
                        if session_id in session_manager.active_sessions:
                            session_manager.active_sessions[session_id][
                                "enable_compression"
                            ] = new_config["enable_compression"]

                await session_manager.update_session_stats(session_id, **new_config)
                await session_manager.broadcast_to_client(
                    client_id,
                    {
                        "type": "config",
                        "config": new_config,
                        "session_id": session_id,
                        "admin": admin_username,
                    },
                )
                logger.info(f"⚙️ 配置已更新: {new_config}")

        elif msg_type == "get_stats":
            stats = session_manager.session_stats.get(session_id, {})
            await session_manager.send_to_session(
                session_id,
                {
                    "type": "stats",
                    "session_id": session_id,
                    "stats": {
                        "frames_sent": stats.get("frames_sent", 0),
                        "bytes_sent": stats.get("bytes_sent", 0),
                        "bytes_sent_mb": round(
                            stats.get("bytes_sent", 0) / (1024 * 1024), 2
                        ),
                        "qr_detected": stats.get("qr_detected", 0),
                        "commands_sent": stats.get("commands_sent", 0),
                        "errors": stats.get("errors", 0),
                        "compressed_frames": stats.get("compressed_frames", 0),
                        "compressed_bytes_saved": stats.get(
                            "compressed_bytes_saved", 0
                        ),
                        "duration": int(
                            time.time()
                            - session_manager.active_sessions.get(session_id, {}).get(
                                "start_time", time.time()
                            )
                        ),
                    },
                    "timestamp": time.time(),
                },
            )

        elif msg_type == "stop_view":
            logger.info(f"📴 管理员停止查看: {session_id}")
            if client_id:
                # 广播管理员离开消息
                await session_manager.broadcast_to_client(
                    client_id,
                    {
                        "type": "admin_left",
                        "admin_user": admin_username,
                        "session_id": session_id,
                        "timestamp": time.time(),
                    },
                )
            # ✅ 主动关闭会话
            await session_manager.close_session(session_id, "管理员停止查看")
            break  # 退出消息循环

        # ✅ 关键：处理前端主动关闭消息
        elif msg_type == "close":
            logger.info(f"🔚 管理员主动关闭会话: {session_id}")
            if client_id:
                # 广播管理员离开消息给客户端，让客户端停止采集
                await session_manager.broadcast_to_client(
                    client_id,
                    {
                        "type": "admin_left",
                        "admin_user": admin_username,
                        "session_id": session_id,
                        "timestamp": time.time(),
                    },
                )
            # 退出消息循环，结束会话
            break

        # ✅ 可选：处理连接断开消息
        elif msg_type == "disconnect":
            logger.info(f"🔌 管理员请求断开连接: {session_id}")
            if client_id:
                await session_manager.broadcast_to_client(
                    client_id,
                    {
                        "type": "admin_left",
                        "admin_user": admin_username,
                        "session_id": session_id,
                        "timestamp": time.time(),
                    },
                )
            break

        else:
            logger.debug(f"未知消息类型: {msg_type}")


@router.websocket("/ws/admin/{employee_id:path}")
async def websocket_admin_endpoint(
    websocket: WebSocket,
    employee_id: str,
    db: Session = Depends(get_db),
):
    """
    管理员WebSocket端点（支持断线重连）
    """
    client_id = None
    session_id = None
    admin_username = None
    reconnect_token = websocket.query_params.get("reconnect_token")

    try:

        # ==================== 断线重连处理 ====================
        if reconnect_token:

            # ✅ 1. 先接受 WebSocket 连接
            await websocket.accept()

            # 2. 验证重连令牌
            token_data = await reconnect_manager.validate_reconnect_token(
                reconnect_token
            )
            if not token_data or not token_data["session_id"]:
                logger.warning("❌ 无效的重连令牌")
                await websocket.close(code=1008, reason="无效的重连令牌")
                return

            # 3. 获取恢复数据
            recovery_data = await reconnect_manager.get_recovery_data(
                token_data["session_id"]
            )
            if not recovery_data:
                logger.warning("❌ 无恢复数据")
                await websocket.close(code=1000, reason="恢复数据已过期")
                return

            # 4. 验证用户身份
            admin_username = recovery_data.get("admin_user")
            client_id = recovery_data.get("client_id")

            # 验证当前 token 中的用户是否匹配
            token = websocket.query_params.get("token")
            if token:
                payload = await verify_websocket_token(token, "admin")
                if not payload or payload.get("sub") != admin_username:
                    logger.warning(f"⚠️ 重连用户不匹配")
                    await websocket.close(code=1008, reason="用户不匹配")
                    return

            # 5. 尝试恢复会话
            recovered_session_id = await session_manager.recover_session(
                token_data["session_id"], websocket, reconnect_token
            )

            if recovered_session_id:
                session_id = recovered_session_id

                # 6. 确认 client_id（从恢复的会话中获取）
                session_info = await session_manager.get_session(session_id)
                if session_info and not client_id:
                    client_id = session_info.get("client_id")

                # 7. 发送恢复确认
                await safe_websocket_send(
                    websocket,
                    {
                        "type": "reconnect_success",
                        "session_id": session_id,
                        "client_id": client_id,
                        "timestamp": time.time(),
                    },
                )

                # 8. 广播观众更新
                if client_id:
                    await _broadcast_viewer_update(client_id)

                # 9. 进入消息处理循环
                await _handle_admin_messages(
                    websocket, session_id, client_id, admin_username
                )
                return  # 处理完成后直接返回
            else:
                logger.warning("❌ 会话恢复失败")
                await websocket.close(code=1000, reason="会话恢复失败，请重新连接")
                return

        # ==================== 正常创建新会话 ====================
        token = websocket.query_params.get("token")
        if not token:
            logger.error("❌ 缺少token参数")
            await websocket.close(code=1008, reason="缺少token")
            return

        decoded_employee_id = urllib.parse.unquote(employee_id)
        sanitized_employee_id = validate_and_sanitize_employee_id(decoded_employee_id)
        if not sanitized_employee_id:
            logger.error(f"❌ 无效的employee_id: {decoded_employee_id}")
            await websocket.close(code=1008, reason="无效的员工ID")
            return

        payload = await verify_websocket_token(token, "admin")
        if not payload:
            logger.error("❌ 令牌验证失败")
            await websocket.close(code=1008, reason="认证失败")
            return

        username = payload.get("sub")
        admin_username = username

        admin_user = (
            db.query(models.User)
            .filter(models.User.username == username, models.User.is_active == True)
            .first()
        )

        if not admin_user:
            logger.warning(f"❌ 用户无效: {username}")
            await websocket.close(code=1008, reason="用户无效")
            return

        employee = (
            db.query(models.Employee)
            .filter(models.Employee.employee_id == sanitized_employee_id)
            .first()
        )

        if not employee:
            logger.warning(f"❌ 员工不存在: {sanitized_employee_id}")
            await websocket.close(code=1004, reason="员工不存在")
            return

        client = (
            db.query(models.Client)
            .filter(models.Client.employee_id == sanitized_employee_id)
            .first()
        )

        if not client:
            logger.warning(f"❌ 员工没有关联客户端: {sanitized_employee_id}")
            await websocket.close(code=1004, reason="员工没有关联客户端")
            return

        client_id = client.client_id

        client_config = client.config or {}
        if not client_config.get("enable_remote_screen", True):
            logger.warning(f"❌ 客户端禁止远程查看: {client_id}")
            await websocket.close(code=1008, reason="客户端禁止远程查看")
            return

        await websocket.accept()
     
        # 检查是否启用压缩
        enable_compression = client_config.get(
            "enable_compression", COMPRESSION_ENABLED
        )
        session_id = await session_manager.create_session(
            websocket,
            sanitized_employee_id,
            client_id,
            username,
            admin_user.id,
            enable_compression=enable_compression,
        )
        async with session_manager._lock:
            sessions = session_manager.client_to_admin.get(client_id, set())
        

        # ✅ 先获取当前观众数
        viewer_count = await session_manager.get_viewer_count(client_id)

        # 广播观众更新
        await _broadcast_viewer_update(client_id)

        # 发送 connected 消息给管理员
        await session_manager.send_to_session(
            session_id,
            {
                "type": "connected",
                "session_id": session_id,
                "employee": {
                    "id": employee.employee_id,
                    "name": employee.name,
                    "computer": client.computer_name,
                },
                "config": {
                    "max_fps": client_config.get("remote_max_fps", 10),
                    "max_quality": client_config.get("remote_max_quality", 95),
                    "enable_diff": client_config.get("remote_enable_diff", True),
                    "enable_qr": client_config.get("remote_enable_qr", False),
                    "enable_compression": enable_compression,
                },
                # ✅ 添加 viewers 字段
                "viewers": viewer_count,
                "timestamp": time.time(),
            },
        )

        # 进入消息处理循环
        await _handle_admin_messages(websocket, session_id, client_id, username)

    except WebSocketDisconnect:
        logger.info(f"⚠️ 管理员WebSocket断开: {employee_id}")
        if session_id:
            await session_manager.close_session(
                session_id, "连接断开", store_recovery=True
            )
    except Exception as e:
        logger.error(f"❌ 管理员WebSocket异常: {e}", exc_info=True)
        if session_id:
            await session_manager.update_session_stats(session_id, errors=1)
    finally:
        if client_id:
            await _broadcast_viewer_update(client_id)


# ==================== 修复后的客户端WebSocket压缩配置保存 ====================
@router.websocket("/ws/client/{client_id}")
async def websocket_client_endpoint(websocket: WebSocket, client_id: str):
    """
    客户端WebSocket端点（支持二进制和文本消息）
    """
    try:
        logger.info(f"💻 客户端连接请求: client_id={client_id}")

        sanitized_client_id = validate_client_id(client_id)
        if not sanitized_client_id:
            logger.error(f"❌ 无效的client_id: {client_id}")
            await websocket.close(code=1008, reason="无效的客户端ID")
            return

        await websocket.accept()
        logger.info(f"✅ 客户端 {sanitized_client_id} 连接成功")

        # 注册客户端WebSocket连接
        await session_manager.register_client_websocket(sanitized_client_id, websocket)

        viewer_count = await session_manager.get_viewer_count(sanitized_client_id)

        # 发送连接成功消息
        await safe_websocket_send(
            websocket,
            {
                "type": "connected",
                "client_id": sanitized_client_id,
                "viewers": viewer_count,
                "config": {
                    "quality": 80,
                    "fps": 5,
                    "enable_diff": True,
                    "enable_h264": True,
                    "enable_qr": False,
                    "enable_compression": COMPRESSION_ENABLED,
                    "compression_level": COMPRESSION_LEVEL,
                    "compression_min_size": COMPRESSION_MIN_SIZE,
                },
                "timestamp": time.time(),
            },
        )

        if viewer_count > 0:
            await safe_websocket_send(
                websocket,
                {
                    "type": "viewer_update",
                    "viewers": viewer_count,
                    "timestamp": time.time(),
                },
            )

        last_heartbeat = time.time()
        client_compression_enabled = COMPRESSION_ENABLED

        while True:
            try:
                # ✅ 关键修复：使用 receive() 而不是 receive_text()
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=WS_HEARTBEAT_INTERVAL
                )

                # ✅ 处理不同类型的消息
                if "text" in message:
                    # 文本消息
                    text_message = message["text"]
                    logger.debug(
                        f"📨 [服务器] 收到客户端文本消息: {text_message[:100]}"
                    )

                    if len(text_message) > WS_MAX_MESSAGE_SIZE:
                        logger.warning(f"消息过大: {len(text_message)} bytes")
                        continue

                    data = safe_json_loads(text_message)
                    if not data:
                        continue

                    msg_type = data.get("type")

                    if msg_type == "frame":
                        # 文本格式的帧（降级方案）
                        valid, error = validate_frame_data(data)
                        if not valid:
                            logger.warning(f"帧数据无效: {error}")
                            continue

                        frame_size = len(text_message.encode())
                        asyncio.create_task(
                            session_manager.forward_frame_to_admins(
                                sanitized_client_id, text_message, frame_size
                            )
                        )

                    elif msg_type == "heartbeat":
                        last_heartbeat = time.time()
                        viewer_count = await session_manager.get_viewer_count(
                            sanitized_client_id
                        )
                        await safe_websocket_send(
                            websocket,
                            {
                                "type": "heartbeat_ack",
                                "viewers": viewer_count,
                                "timestamp": time.time(),
                            },
                        )

                    elif msg_type == "qr_detected":
                        items = await session_manager.get_websockets_by_client(
                            sanitized_client_id
                        )
                        if items:
                            for _, sender in items:
                                asyncio.create_task(sender.send(data))
                                # 注意：这里需要 session_id，但 qr_detected 没有 session_id
                                # await session_manager.update_session_stats(sid, qr_detected=1)

                    elif msg_type == "ping":
                        await safe_websocket_send(
                            websocket,
                            {
                                "type": "pong",
                                "timestamp": data.get("timestamp", time.time()),
                            },
                        )

                    elif msg_type == "client_info":
                        capabilities = data.get("capabilities", {})
                        logger.info(f"📋 客户端能力信息: {capabilities}")

                        if "enable_compression" in capabilities:
                            client_compression_enabled = capabilities[
                                "enable_compression"
                            ]
                            logger.info(
                                f"客户端压缩配置: {'启用' if client_compression_enabled else '禁用'}"
                            )

                    elif msg_type == "stats":
                        logger.debug(f"📊 客户端统计: {data.get('stats', {})}")

                    elif msg_type == "close":
                        logger.info(f"🔚 客户端主动关闭: {sanitized_client_id}")
                        break

                elif "bytes" in message:
                    # ✅ 二进制消息 - 直接转发给管理员
                    binary_data = message["bytes"]
                    logger.info(
                        f"📨 [服务器] 收到客户端二进制帧: {len(binary_data)} bytes"
                    )

                    # 直接转发给所有管理员
                    items = await session_manager.get_websockets_by_client(
                        sanitized_client_id
                    )
                    if items:
                        for sid, sender in items:
                            try:
                                if hasattr(sender, "websocket"):
                                    await sender.websocket.send_bytes(binary_data)
                                elif hasattr(sender, "send_bytes"):
                                    await sender.send_bytes(binary_data)
                                # 更新统计
                                asyncio.create_task(
                                    session_manager.update_frame_stats(
                                        sid, len(binary_data)
                                    )
                                )
                            except Exception as e:
                                logger.debug(f"二进制转发失败 sid={sid}: {e}")
                    else:
                        logger.debug(f"⚠️ 没有管理员会话，跳过二进制转发")

            except asyncio.TimeoutError:
                if time.time() - last_heartbeat > WS_IDLE_TIMEOUT:
                    logger.info(f"⏰ 客户端空闲超时: {sanitized_client_id}")
                    break
                continue
            except Exception as e:
                logger.error(f"接收消息异常: {e}")
                break

    except WebSocketDisconnect:
        logger.info(f"⚠️ 客户端WebSocket断开: {client_id}")
    except Exception as e:
        logger.error(f"❌ 客户端WebSocket异常: {e}", exc_info=True)
    finally:
        # 注销客户端WebSocket连接
        await session_manager.unregister_client_websocket(client_id)
        await session_manager.close_all_sessions_for_client(client_id, "客户端断开")
        await _broadcast_viewer_update(client_id)


# ==================== HTTP接口（增强版）====================
@router.get("/clients/online", tags=["远程屏幕"])
async def get_online_clients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取可查看的在线客户端"""
    beijing_now = get_beijing_now()
    cutoff = beijing_now - timedelta(minutes=10)

    clients = (
        db.query(models.Client)
        .filter(models.Client.last_seen >= cutoff)
        .order_by(models.Client.last_seen.desc())
        .all()
    )

    result = []
    for client in clients:
        employee = (
            db.query(models.Employee)
            .filter(models.Employee.employee_id == client.employee_id)
            .first()
        )

        if not employee:
            continue

        client_config = client.config or {}
        if not client_config.get("enable_remote_screen", True):
            continue

        viewer_count = await session_manager.get_viewer_count(client.client_id)
        sessions = await session_manager.get_sessions_by_client(client.client_id)
        admins = [s.get("admin_user") for s in sessions if s.get("admin_user")]

        result.append(
            {
                "client_id": client.client_id,
                "employee_id": client.employee_id,
                "employee_name": employee.name,
                "computer_name": client.computer_name,
                "windows_user": client.windows_user,
                "ip_address": client.ip_address,
                "last_seen": client.last_seen.isoformat() if client.last_seen else None,
                "is_online": True,
                "is_viewing": viewer_count > 0,
                "viewer_count": viewer_count,
                "admins": admins,
                "capabilities": {
                    "diff_frame": client_config.get("remote_enable_diff", True),
                    "region_detect": client_config.get("remote_enable_region", True),
                    "h264": client_config.get("remote_enable_h264", True),
                    "qr_detect": client_config.get("remote_enable_qr", False),
                    "max_fps": client_config.get("remote_max_fps", 10),
                    "max_quality": client_config.get("remote_max_quality", 95),
                    "enable_compression": client_config.get(
                        "enable_compression", COMPRESSION_ENABLED
                    ),
                },
            }
        )

    return {"items": result, "total": len(result)}


@router.get("/employees/{employee_id:path}/can-view", tags=["远程屏幕"])
async def can_view_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """检查是否可以查看员工（支持路径中的特殊字符）"""
    try:
        logger.info(f"🔍 检查是否可以查看: {employee_id}")

        decoded_id = urllib.parse.unquote(employee_id)
        sanitized_id = validate_and_sanitize_employee_id(decoded_id)

        if not sanitized_id:
            logger.warning(f"❌ 无效的employee_id: {decoded_id}")
            return {"can_view": False, "reason": "无效的员工ID"}

        employee = (
            db.query(models.Employee)
            .filter(models.Employee.employee_id == sanitized_id)
            .first()
        )

        if not employee:
            logger.warning(f"❌ 员工不存在: {sanitized_id}")
            return {"can_view": False, "reason": "员工不存在"}

        beijing_now = get_beijing_now()
        cutoff = beijing_now - timedelta(minutes=10)

        online_client = (
            db.query(models.Client)
            .filter(
                models.Client.employee_id == sanitized_id,
                models.Client.last_seen >= cutoff,
            )
            .first()
        )

        any_client = (
            db.query(models.Client)
            .filter(models.Client.employee_id == sanitized_id)
            .first()
        )

        if not any_client:
            logger.warning(f"❌ 没有关联的客户端: {sanitized_id}")
            return {"can_view": False, "reason": "没有关联的客户端"}

        client_to_check = online_client or any_client
        client_config = client_to_check.config or {}

        if not client_config.get("enable_remote_screen", True):
            logger.warning(f"❌ 客户端禁止远程查看: {client_to_check.client_id}")
            return {"can_view": False, "reason": "客户端禁止远程查看"}

        if not online_client:
            if any_client.last_seen:
                minutes_ago = (beijing_now - any_client.last_seen).total_seconds() / 60
                return {
                    "can_view": False,
                    "reason": f"客户端离线 ({int(minutes_ago)}分钟前)",
                    "client_id": any_client.client_id,
                    "last_seen": any_client.last_seen.isoformat(),
                }
            else:
                return {"can_view": False, "reason": "客户端从未在线"}

        viewer_count = await session_manager.get_viewer_count(online_client.client_id)
        sessions = await session_manager.get_sessions_by_client(online_client.client_id)
        admins = [s.get("admin_user") for s in sessions if s.get("admin_user")]

        capabilities = {
            "diff_frame": client_config.get("remote_enable_diff", True),
            "region_detect": client_config.get("remote_enable_region", True),
            "h264": client_config.get("remote_enable_h264", True),
            "qr_detect": client_config.get("remote_enable_qr", False),
            "max_fps": client_config.get("remote_max_fps", 10),
            "max_quality": client_config.get("remote_max_quality", 95),
            "enable_compression": client_config.get(
                "enable_compression", COMPRESSION_ENABLED
            ),
        }

        logger.info(f"✅ 可以查看: {sanitized_id}, 客户端: {online_client.client_id}")

        return {
            "can_view": True,
            "client_id": online_client.client_id,
            "employee_name": employee.name,
            "is_viewing": viewer_count > 0,
            "viewer_count": viewer_count,
            "admins": admins,
            "capabilities": capabilities,
        }

    except Exception as e:
        logger.error(f"❌ can_view_employee 异常: {e}", exc_info=True)
        return {"can_view": False, "reason": "服务器内部错误"}


@router.get("/sessions/active", tags=["远程屏幕"])
async def get_active_sessions(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的活跃会话"""
    sessions = await session_manager.get_sessions_by_admin(current_user.username)

    result = []
    for session in sessions:
        stats = session_manager.session_stats.get(session["session_id"], {})

        employee = (
            db.query(models.Employee)
            .filter(models.Employee.employee_id == session["employee_id"])
            .first()
        )

        client = (
            db.query(models.Client)
            .filter(models.Client.client_id == session["client_id"])
            .first()
        )

        result.append(
            {
                "session_id": session["session_id"],
                "employee_id": session["employee_id"],
                "employee_name": employee.name if employee else "未知",
                "client_id": session["client_id"],
                "computer_name": client.computer_name if client else "未知",
                "start_time": session["start_time"],
                "start_time_str": datetime.fromtimestamp(
                    session["start_time"]
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "last_heartbeat": session["last_heartbeat"],
                "last_heartbeat_str": datetime.fromtimestamp(
                    session["last_heartbeat"]
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "duration": int(time.time() - session["start_time"]),
                "quality": session.get("quality", 80),
                "fps": session.get("fps", 5),
                "width": session.get("width", 1280),
                "height": session.get("height", 720),
                "network_quality": session.get("network_quality", 100),
                "enable_compression": session.get("enable_compression", False),
                "stats": {
                    "frames_sent": stats.get("frames_sent", 0),
                    "bytes_sent": stats.get("bytes_sent", 0),
                    "bytes_sent_mb": round(
                        stats.get("bytes_sent", 0) / (1024 * 1024), 2
                    ),
                    "qr_detected": stats.get("qr_detected", 0),
                    "commands_sent": stats.get("commands_sent", 0),
                    "errors": stats.get("errors", 0),
                    "compressed_frames": stats.get("compressed_frames", 0),
                    "compressed_bytes_saved": stats.get("compressed_bytes_saved", 0),
                },
            }
        )

    return {"items": result, "total": len(result)}


@router.get("/sessions/all", tags=["远程屏幕"])
async def get_all_sessions(
    current_user: models.User = Depends(get_current_active_user),
    limit: int = 100,
):
    """获取所有活跃会话（管理员专用）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    all_sessions = []
    async with session_manager._lock:
        for session_id, session in session_manager.active_sessions.items():
            all_sessions.append(
                {
                    "session_id": session_id,
                    "employee_id": session["employee_id"],
                    "client_id": session["client_id"],
                    "admin_user": session["admin_user"],
                    "start_time": session["start_time"],
                    "start_time_str": datetime.fromtimestamp(
                        session["start_time"]
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "duration": int(time.time() - session["start_time"]),
                    "status": session.get("status", "active"),
                    "last_heartbeat": session.get("last_heartbeat", 0),
                    "quality": session.get("quality", 80),
                    "fps": session.get("fps", 5),
                    "enable_compression": session.get("enable_compression", False),
                }
            )

    all_sessions.sort(key=lambda x: x["start_time"], reverse=True)

    return {"items": all_sessions[:limit], "total": len(all_sessions), "limit": limit}


@router.post("/sessions/{session_id}/control", tags=["远程屏幕"])
async def control_session(
    session_id: str,
    command: dict,
    current_user: models.User = Depends(get_current_active_user),
):
    """控制远程会话"""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session["admin_user"] != current_user.username:
        raise HTTPException(status_code=403, detail="无权操作此会话")

    safe_command = {
        "type": "command",
        "command": command.get("command"),
        "params": command.get("params", {}),
        "session_id": session_id,
        "admin": current_user.username,
        "timestamp": time.time(),
    }

    await session_manager.broadcast_to_client(
        session["client_id"],
        safe_command,
    )

    await session_manager.update_session_stats(session_id, commands_sent=1)

    return {"message": "命令已发送", "session_id": session_id}


@router.delete("/sessions/{session_id}", tags=["远程屏幕"])
async def close_session_api(
    session_id: str,
    current_user: models.User = Depends(get_current_active_user),
):
    """关闭远程会话"""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session["admin_user"] != current_user.username:
        raise HTTPException(status_code=403, detail="无权操作此会话")

    await session_manager.close_session(session_id, "管理员手动关闭")

    return {"message": "会话已关闭", "session_id": session_id}


@router.post("/sessions/{session_id}/quality", tags=["远程屏幕"])
async def set_session_quality(
    session_id: str,
    quality_data: dict,
    current_user: models.User = Depends(get_current_active_user),
):
    """设置会话画质"""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session["admin_user"] != current_user.username:
        raise HTTPException(status_code=403, detail="无权操作此会话")

    quality = quality_data.get("quality", 80)
    fps = quality_data.get("fps", 5)

    quality = max(1, min(100, quality))
    fps = max(1, min(30, fps))

    await session_manager.update_session_stats(session_id, quality=quality, fps=fps)

    await session_manager.broadcast_to_client(
        session["client_id"],
        {
            "type": "config",
            "config": {"quality": quality, "fps": fps},
            "session_id": session_id,
            "admin": current_user.username,
        },
    )

    return {
        "message": "画质已更新",
        "quality": quality,
        "fps": fps,
        "session_id": session_id,
    }


@router.post("/sessions/close-all", tags=["远程屏幕"])
async def close_all_sessions(
    current_user: models.User = Depends(get_current_active_user),
):
    """关闭当前用户的所有会话"""
    sessions = await session_manager.get_sessions_by_admin(current_user.username)

    close_tasks = []
    for session in sessions:
        close_tasks.append(
            session_manager.close_session(session["session_id"], "用户批量关闭")
        )

    if close_tasks:
        await asyncio.gather(*close_tasks, return_exceptions=True)

    return {
        "message": f"已关闭 {len(close_tasks)} 个会话",
        "closed_count": len(close_tasks),
    }


@router.get("/sessions/{session_id}/status", tags=["远程屏幕"])
async def get_session_status(
    session_id: str,
    current_user: models.User = Depends(get_current_active_user),
):
    """获取会话状态详情"""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session["admin_user"] != current_user.username:
        raise HTTPException(status_code=403, detail="无权查看此会话")

    stats = session_manager.session_stats.get(session_id, {})

    return {
        "session_id": session_id,
        "status": session.get("status", "active"),
        "start_time": session["start_time"],
        "duration": int(time.time() - session["start_time"]),
        "last_heartbeat": session["last_heartbeat"],
        "last_frame_time": session.get("last_frame_time", 0),
        "quality": session.get("quality", 80),
        "fps": session.get("fps", 5),
        "network_quality": session.get("network_quality", 100),
        "enable_compression": session.get("enable_compression", False),
        "stats": {
            "frames_sent": stats.get("frames_sent", 0),
            "bytes_sent": stats.get("bytes_sent", 0),
            "bytes_sent_mb": round(stats.get("bytes_sent", 0) / (1024 * 1024), 2),
            "qr_detected": stats.get("qr_detected", 0),
            "commands_sent": stats.get("commands_sent", 0),
            "errors": stats.get("errors", 0),
            "compressed_frames": stats.get("compressed_frames", 0),
            "compressed_bytes_saved": stats.get("compressed_bytes_saved", 0),
            "compressed_bytes_saved_mb": round(
                stats.get("compressed_bytes_saved", 0) / (1024 * 1024), 2
            ),
        },
    }


# ==================== 调试接口（增强版）====================
@router.get("/debug/clients", tags=["调试"])
async def debug_get_all_clients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """调试接口：获取所有客户端（包括离线）"""
    try:
        clients = (
            db.query(models.Client)
            .order_by(models.Client.last_seen.desc())
            .limit(50)
            .all()
        )

        result = []
        beijing_now = get_beijing_now()

        for client in clients:
            employee = (
                db.query(models.Employee)
                .filter(models.Employee.employee_id == client.employee_id)
                .first()
            )

            is_online = False
            if client.last_seen:
                is_online = (beijing_now - client.last_seen) < timedelta(minutes=10)

            result.append(
                {
                    "client_id": client.client_id,
                    "employee_id": client.employee_id,
                    "employee_name": employee.name if employee else None,
                    "computer_name": client.computer_name,
                    "last_seen": (
                        client.last_seen.isoformat() if client.last_seen else None
                    ),
                    "is_online": is_online,
                    "last_seen_minutes_ago": (
                        (beijing_now - client.last_seen).total_seconds() / 60
                        if client.last_seen
                        else None
                    ),
                }
            )

        return {
            "total": len(result),
            "current_time": beijing_now.isoformat(),
            "online_threshold_minutes": 10,
            "clients": result,
        }
    except Exception as e:
        logger.error(f"调试接口错误: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/debug/check-client/{client_id}", tags=["调试"])
async def debug_check_client(
    client_id: str,
    db: Session = Depends(get_db),
):
    """调试：检查特定客户端的状态"""
    try:
        client = (
            db.query(models.Client).filter(models.Client.client_id == client_id).first()
        )

        if not client:
            return {"error": "客户端不存在"}

        employee = (
            db.query(models.Employee)
            .filter(models.Employee.employee_id == client.employee_id)
            .first()
        )

        beijing_now = get_beijing_now()
        is_online = False
        minutes_ago = None
        if client.last_seen:
            minutes_ago = (beijing_now - client.last_seen).total_seconds() / 60
            is_online = minutes_ago < 10

        sessions = await session_manager.get_sessions_by_client(client_id)

        return {
            "client": {
                "client_id": client.client_id,
                "employee_id": client.employee_id,
                "employee_name": employee.name if employee else None,
                "computer_name": client.computer_name,
                "last_seen": client.last_seen.isoformat() if client.last_seen else None,
                "minutes_ago": minutes_ago,
                "is_online": is_online,
                "config": client.config,
            },
            "sessions": {
                "count": len(sessions),
                "is_viewing": len(sessions) > 0,
                "viewer_count": len(sessions),
                "admins": [
                    s.get("admin_user") for s in sessions if s.get("admin_user")
                ],
            },
            "current_time": beijing_now.isoformat(),
            "online_threshold_minutes": 10,
        }
    except Exception as e:
        logger.error(f"调试接口错误: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/debug/stats", tags=["调试"])
async def debug_get_stats(
    current_user: models.User = Depends(get_current_active_user),
):
    """调试：获取全局统计信息"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    async with session_manager._lock:
        total_sessions = len(session_manager.active_sessions)
        total_clients = len(session_manager.client_to_admin)
        total_admins = len(session_manager.admin_to_sessions)

        total_frames = sum(
            s.get("frames_sent", 0) for s in session_manager.session_stats.values()
        )
        total_bytes = sum(
            s.get("bytes_sent", 0) for s in session_manager.session_stats.values()
        )
        total_qr = sum(
            s.get("qr_detected", 0) for s in session_manager.session_stats.values()
        )
        total_compressed_frames = sum(
            s.get("compressed_frames", 0)
            for s in session_manager.session_stats.values()
        )
        total_compressed_saved = sum(
            s.get("compressed_bytes_saved", 0)
            for s in session_manager.session_stats.values()
        )

        sessions_list = []
        for sid, session in list(session_manager.active_sessions.items())[:20]:
            stats = session_manager.session_stats.get(sid, {})
            sessions_list.append(
                {
                    "session_id": sid,
                    "employee_id": session["employee_id"],
                    "admin_user": session["admin_user"],
                    "duration": int(time.time() - session["start_time"]),
                    "frames": stats.get("frames_sent", 0),
                    "bytes_mb": round(stats.get("bytes_sent", 0) / (1024 * 1024), 2),
                    "compressed_frames": stats.get("compressed_frames", 0),
                }
            )

    return {
        "total_sessions": total_sessions,
        "total_clients": total_clients,
        "total_admins": total_admins,
        "total_frames": total_frames,
        "total_bytes": total_bytes,
        "total_bytes_mb": round(total_bytes / (1024 * 1024), 2),
        "total_qr_detected": total_qr,
        "compression_stats": {
            "enabled": COMPRESSION_ENABLED,
            "compressed_frames": total_compressed_frames,
            "compression_ratio": f"{total_compressed_frames / max(total_frames, 1) * 100:.1f}%",
            "bytes_saved": total_compressed_saved,
            "bytes_saved_mb": round(total_compressed_saved / (1024 * 1024), 2),
        },
        "active_sessions": sessions_list,
        "timestamp": time.time(),
    }


@router.get("/debug/reconnect-tokens", tags=["调试"])
async def debug_get_reconnect_tokens(
    current_user: models.User = Depends(get_current_active_user),
):
    """调试：获取当前有效的重连令牌"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    async with reconnect_manager._lock:
        tokens = []
        for token, data in reconnect_manager._reconnect_tokens.items():
            tokens.append(
                {
                    "token": token[:20] + "...",
                    "session_id": data["session_id"],
                    "employee_id": data["employee_id"],
                    "admin_user": data["admin_user"],
                    "expiry": data["expiry"],
                    "expiry_str": datetime.fromtimestamp(data["expiry"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "remaining": max(0, int(data["expiry"] - time.time())),
                }
            )

    return {
        "active_tokens": len(tokens),
        "tokens": tokens,
        "timestamp": time.time(),
    }


# ==================== 导出 ====================
__all__ = [
    "router",
    "session_manager",
    "start_remote_service",
    "shutdown_remote_service",
]
