# server_schemas.py - 修复版（移除 dateutil 依赖）

"""
Pydantic数据验证模型
"""

from pydantic import BaseModel, Field, validator
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import re


# ==================== 用户相关 ====================


class UserBase(BaseModel):
    username: str
    role: str = "user"


class UserCreate(UserBase):
    password: str

    @validator("password")
    def password_length(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少6个字符")
        return v


class User(UserBase):
    id: int
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    is_active: bool = True
    department: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    last_ip: Optional[str] = None
    role_id: Optional[int] = None
    role_name: Optional[str] = None
    permissions: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str
    user: Optional[Dict[str, Any]] = None


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


# ==================== 员工相关 ====================


class EmployeeBase(BaseModel):
    employee_id: str
    name: str
    computer_name: Optional[str] = None
    windows_user: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: str = "active"


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    computer_name: Optional[str] = None
    windows_user: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None


class Employee(EmployeeBase):
    total_screenshots: Optional[int] = 0
    today_screenshots: Optional[int] = 0
    online_clients: Optional[int] = 0
    last_active: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== 客户端相关 ====================


class ClientBase(BaseModel):
    client_id: Optional[str] = None
    computer_name: Optional[str] = None
    windows_user: Optional[str] = None
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    os_version: Optional[str] = None
    cpu_id: Optional[str] = None
    disk_serial: Optional[str] = None
    client_version: Optional[str] = None
    first_seen: Optional[datetime] = None
    fingerprint_history: Optional[List[dict]] = []
    ip_history: Optional[List[dict]] = []
    review_flags: Optional[List[dict]] = []


class ClientCreate(ClientBase):
    interval: Optional[int] = None
    quality: Optional[int] = None
    format: Optional[str] = None
    employee_name: Optional[str] = None
    capabilities: Optional[List[str]] = []

    hardware_fingerprint: Optional[str] = None
    hardware_parts: Optional[List[str]] = None
    has_hardware: Optional[bool] = False


class Client(ClientBase):
    employee_id: Optional[str] = None
    last_seen: Optional[datetime] = None
    is_online: Optional[bool] = False
    config: Optional[Dict[str, Any]] = None
    capabilities: List[str] = []
    created_at: Optional[datetime] = None
    client_metadata: Optional[Dict[str, Any]] = None
    first_seen: Optional[datetime] = None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
        extra = "ignore"


# ========== 🚀 修复：增强 Heartbeat 模型，不使用 dateutil ==========
class Heartbeat(BaseModel):
    status: str = "online"
    stats: Optional[Dict[str, Any]] = None
    client_stats: Optional[Dict[str, Any]] = None
    paused: bool = False
    ip_address: Optional[str] = None
    timestamp: Optional[Any] = None

    @validator("timestamp", pre=True, always=True)
    def parse_timestamp(cls, v):
        """智能解析时间戳，不使用外部依赖"""
        if v is None:
            return None

        # 如果已经是datetime对象
        if isinstance(v, datetime):
            return v

        # 如果是字符串，尝试解析
        if isinstance(v, str):
            # 处理 ISO 格式 (2026-03-12T13:30:00 或 2026-03-12 13:30:00)
            # 替换 'T' 为空格，处理 'Z' 结尾
            v = v.replace("T", " ").replace("Z", "")

            # 尝试不同的格式
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y%m%d_%H%M%S",
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue

            # 如果都失败，返回当前UTC时间
            return datetime.now(timezone.utc)

        # 其他类型，返回当前时间
        return datetime.now(timezone.utc)

    @validator("paused", pre=True, always=True)
    def parse_paused(cls, v):
        """确保paused是布尔值"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)


# ==================== 截图相关 ====================


class ScreenshotBase(BaseModel):
    employee_id: str
    client_id: Optional[str] = None
    computer_name: Optional[str] = None
    windows_user: Optional[str] = None
    filename: str
    file_size: int = 0
    width: int = 0
    height: int = 0
    image_format: str = "webp"
    is_encrypted: bool = False


class ScreenshotCreate(ScreenshotBase):
    screenshot_time: Optional[datetime] = None


class Screenshot(ScreenshotBase):
    id: int
    thumbnail: Optional[str] = None
    storage_url: Optional[str] = None
    uploaded_at: datetime
    screenshot_time: datetime
    url: Optional[str] = None
    time: Optional[str] = None
    date: Optional[str] = None
    datetime: Optional[str] = None
    size_str: Optional[str] = None
    format: Optional[str] = None
    encrypted: Optional[bool] = None
    name: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== 统计相关 ====================


class Stats(BaseModel):
    today: int
    yesterday: int
    week: int
    total: int
    employees: int
    clients: int
    online: int
    storage_mb: float
    image_formats: Dict[str, int]
    hourly: List[int]
    recent_activities: List[Dict[str, str]]
    top_employees: List[Dict[str, Any]]
    auto_cleanup: Dict[str, Any]


class Activity(BaseModel):
    id: int
    employee_id: Optional[str] = None
    action: str
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== 清理相关 ====================


class CleanupStatus(BaseModel):
    enabled: bool
    retention_hours: int
    interval_hours: float
    pending_cleanup: int
    pending_size_mb: float
    last_cleanup: Optional[str] = None


# ==================== 通知相关 ====================


class NotificationBase(BaseModel):
    title: str
    content: Optional[str] = None
    type: str = "info"
    category: str = "system"
    related_id: Optional[str] = None
    related_type: Optional[str] = None
    action_url: Optional[str] = None
    action_text: Optional[str] = None
    expires_at: Optional[datetime] = None


class NotificationCreate(NotificationBase):
    user_id: int


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None
    read_at: Optional[datetime] = None


class Notification(NotificationBase):
    id: int
    user_id: int
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[Notification]
    total: int
    skip: int = 0
    limit: int = 20
    has_more: bool = False


class UnreadCountResponse(BaseModel):
    count: int


# ==================== 浏览器历史 ====================
class BrowserHistoryBase(BaseModel):
    employee_id: Optional[str] = None
    client_id: Optional[str] = None
    url: str
    title: Optional[str] = None
    browser: Optional[str] = None
    duration: int = 0
    visit_time: datetime


class BrowserHistoryCreate(BrowserHistoryBase):
    pass


class BrowserHistory(BrowserHistoryBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== 软件使用 ====================
class AppUsageBase(BaseModel):
    employee_id: Optional[str] = None
    client_id: Optional[str] = None
    app_name: str
    app_path: Optional[str] = None
    window_title: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: int = 0
    is_foreground: bool = False
    cpu_avg: int = 0
    memory_avg: int = 0


class AppUsageCreate(AppUsageBase):
    pass


class AppUsage(AppUsageBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== 文件操作 ====================
class FileOperationBase(BaseModel):
    employee_id: Optional[str] = None
    client_id: Optional[str] = None
    operation: str
    file_path: str
    file_name: Optional[str] = None
    file_size: int = 0
    file_type: Optional[str] = None
    is_directory: bool = False
    operation_time: datetime


class FileOperationCreate(FileOperationBase):
    pass


class FileOperation(FileOperationBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
