"""
数据库模型定义
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    JSON,
    BigInteger,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from server_database import Base
from datetime import datetime, timedelta
from server_config import Config
from server_timezone import (
    get_utc_now,
    to_beijing_time,
    make_aware,
    make_naive,
    BEIJING_TZ,
    UTC,
)


# server_models.py - 修改 User 类


class User(Base):
    """用户表（管理员）"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # 保留兼容性
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    permissions = Column(JSON, default={"type": "none"})
    department = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    last_ip = Column(String(45), nullable=True)

    # 关联
    role_rel = relationship("Role", back_populates="users")
    notifications = relationship("Notification", back_populates="user")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "role_id": self.role_id,
            "role_name": self.role_rel.display_name if self.role_rel else None,
            "department": self.department,
            "phone": self.phone,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "last_ip": self.last_ip,
            "is_active": self.is_active,
            "permissions": self.effective_permissions,
        }

    @property
    def effective_permissions(self):
        """获取有效权限（角色权限 + 用户自定义权限覆盖）"""
        # 获取角色权限
        role_perms = self.role_rel.permissions if self.role_rel else {"type": "none"}

        # 获取用户自定义权限
        user_perms = self.permissions if self.permissions else {"type": "none"}

        # ✅ 修复：只有当用户有实际的自定义权限列表时才覆盖
        # 检查用户权限类型是否为 "custom" 且有具体的权限列表
        if (
            user_perms.get("type") == "custom"
            and user_perms.get("permissions")
            and len(user_perms.get("permissions", [])) > 0
        ):
            return user_perms

        # 否则返回角色权限
        return role_perms


class Employee(Base):
    """员工表"""

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    computer_name = Column(String(100))
    windows_user = Column(String(100))
    department = Column(String(50))
    position = Column(String(50))
    email = Column(String(100))
    phone = Column(String(20))
    status = Column(String(20), default="active")  # active, inactive, deleted
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联
    screenshots = relationship(
        "Screenshot", back_populates="employee", cascade="all, delete-orphan"
    )
    clients = relationship(
        "Client", back_populates="employee", cascade="all, delete-orphan"
    )
    activities = relationship(
        "Activity", back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def total_screenshots(self):
        return len(self.screenshots)

    @property
    def today_screenshots(self):
        """今日截图数量 - 修复版"""
        from server_timezone import get_utc_now, make_naive

        now_utc = get_utc_now()  # aware
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # 转换为 naive
        today_start_naive = make_naive(today_start)
        today_end_naive = make_naive(today_end)

        count = 0
        for s in self.screenshots:
            # 确保 screenshot_time 也是 naive
            shot_time = s.screenshot_time
            if shot_time.tzinfo is not None:
                shot_time = shot_time.replace(tzinfo=None)

            if today_start_naive <= shot_time < today_end_naive:
                count += 1

        return count

    @property
    def last_active(self):
        """最后活跃时间"""
        if not self.screenshots:
            return None
        # 返回 aware 时间
        last = max(s.screenshot_time for s in self.screenshots)
        return make_aware(last, BEIJING_TZ)

    @property
    def online_clients(self):
        """在线客户端数量 - 修复版"""
        from server_timezone import get_utc_now, make_naive

        now_naive = make_naive(get_utc_now())

        count = 0
        for c in self.clients:
            if c.last_seen:
                last_naive = make_naive(c.last_seen)
                if (now_naive - last_naive) < timedelta(minutes=10):
                    count += 1
        return count

    def to_dict(self):
        """增强的 to_dict 方法"""
        from server_timezone import format_beijing_time

        return {
            "id": self.employee_id,
            "name": self.name,
            "computer_name": self.computer_name,
            "windows_user": self.windows_user,
            "department": self.department,
            "position": self.position,
            "email": self.email,
            "phone": self.phone,
            "status": self.status,
            "total_screenshots": self.total_screenshots,
            "today_screenshots": self.today_screenshots,
            "online_clients": self.online_clients,
            "client_count": len(self.clients),
            "has_active_clients": self.has_active_clients,
            "is_online": self.has_active_clients,  # 别名，方便前端
            "last_active": (
                format_beijing_time(self.last_active) if self.last_active else None
            ),
            "last_active_client": (
                {
                    "client_id": self.last_active_client.client_id,
                    "computer_name": self.last_active_client.computer_name,
                    "last_seen": format_beijing_time(self.last_active_client.last_seen),
                }
                if self.last_active_client
                else None
            ),
            "created_at": format_beijing_time(self.created_at),
        }

    @property
    def client_count(self):
        """获取关联的客户端数量"""
        return len(self.clients)

    @property
    def has_active_clients(self):
        """是否有活跃客户端 - 修复版"""
        if not self.clients:
            return False

        from server_timezone import get_utc_now, make_naive

        now_naive = make_naive(get_utc_now())

        for client in self.clients:
            if client.last_seen:
                last_naive = make_naive(client.last_seen)
                if (now_naive - last_naive) < timedelta(minutes=10):
                    return True
        return False

    @property
    def last_active_client(self):
        """最后活跃的客户端"""
        if not self.clients:
            return None

        # 过滤掉没有 last_seen 的客户端
        active_clients = [c for c in self.clients if c.last_seen]
        if not active_clients:
            return None

        # 返回最后活跃时间最晚的客户端
        return max(active_clients, key=lambda c: c.last_seen)


class Client(Base):
    """客户端表"""

    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String(64), unique=True, nullable=False, index=True)
    employee_id = Column(
        String(100), ForeignKey("employees.employee_id", ondelete="SET NULL")
    )
    computer_name = Column(String(100))
    windows_user = Column(String(100))
    mac_address = Column(String(17))
    ip_address = Column(String(45))
    os_version = Column(String(100))
    cpu_id = Column(String(100))
    disk_serial = Column(String(100))
    client_version = Column(String(20))
    last_seen = Column(DateTime(timezone=True), default=func.now(), index=True)
    last_stats = Column(JSON, nullable=True)

    # ===== 新增：硬件指纹字段 =====
    hardware_fingerprint = Column(String(64), index=True, nullable=True)
    hardware_parts = Column(JSON, nullable=True)
    has_hardware = Column(Boolean, default=False)
    # =============================

    first_seen = Column(DateTime(timezone=True), nullable=True)  # 首次注册时间
    fingerprint_history = Column(JSON, default=[])  # 硬件指纹历史
    ip_history = Column(JSON, default=[])  # IP历史
    review_flags = Column(JSON, default=[])  # 审核标记
    client_metadata = Column(JSON, default={})

    config = Column(
        JSON,
        default=lambda: {
            "interval": Config.SCREENSHOT_INTERVAL,
            "quality": Config.SCREENSHOT_QUALITY,
            "format": Config.SCREENSHOT_FORMAT,
            "enable_heartbeat": True,
            "enable_batch_upload": True,
        },
    )

    enable_remote_screen = Column(Boolean, default=True)  # 是否允许远程查看
    remote_screen_settings = Column(
        JSON,
        default={
            "max_fps": 10,
            "min_fps": 1,
            "max_quality": 95,
            "min_quality": 30,
            "enable_diff": True,
            "enable_region": True,
            "enable_h264": True,
            "enable_qr": False,
        },
    )

    capabilities = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联
    employee = relationship("Employee", back_populates="clients")
    screenshots = relationship("Screenshot", back_populates="client")

    def _get_naive_last_seen(self):
        """获取 naive 版本的 last_seen（辅助方法）"""
        if not self.last_seen:
            return None
        if self.last_seen.tzinfo is not None:
            return self.last_seen.replace(tzinfo=None)
        return self.last_seen

    @property
    def is_online(self):
        """是否在线 - 修复版"""
        if not self.last_seen:
            return False

        from server_timezone import get_utc_now, make_naive

        # 获取当前UTC时间并确保是 naive
        now_naive = make_naive(get_utc_now())

        # 获取 naive 版本的 last_seen
        last_naive = self._get_naive_last_seen()

        return (now_naive - last_naive) < timedelta(minutes=10)

    def to_dict(self):
        """转换为字典 - 修复版"""
        from server_timezone import format_beijing_time

        # 获取 last_seen 的 ISO 格式（用于显示）
        last_seen_iso = None
        if self.last_seen:
            # 转换为北京时间用于显示
            last_seen_beijing = to_beijing_time(self.last_seen)
            last_seen_iso = last_seen_beijing.isoformat()

        return {
            "client_id": self.client_id,
            "employee_id": self.employee_id,
            "computer_name": self.computer_name,
            "windows_user": self.windows_user,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "os_version": self.os_version,
            "client_version": self.client_version,
            "last_seen": last_seen_iso,  # 北京时间 ISO 格式
            "is_online": self.is_online,  # 现在正确计算
            "config": self.config,
            "capabilities": self.capabilities,
            "created_at": (
                format_beijing_time(self.created_at) if self.created_at else None
            ),
            "hardware_fingerprint": self.hardware_fingerprint,
            "hardware_parts": self.hardware_parts,
            "has_hardware": self.has_hardware,
            "client_metadata": self.client_metadata,
            "first_seen": (
                format_beijing_time(self.first_seen) if self.first_seen else None
            ),
        }


class Screenshot(Base):
    """截图表"""

    __tablename__ = "screenshots"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        String(100),
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id = Column(
        String(64), ForeignKey("clients.client_id", ondelete="SET NULL"), nullable=True
    )
    filename = Column(String(255), nullable=False)
    thumbnail = Column(String(255), nullable=True)
    file_size = Column(BigInteger, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    storage_url = Column(String(500))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    screenshot_time = Column(DateTime(timezone=True), nullable=False, index=True)
    computer_name = Column(String(100))
    windows_user = Column(String(100))
    image_format = Column(String(10), default="webp")
    is_encrypted = Column(Boolean, default=False)

    # 关联
    employee = relationship("Employee", back_populates="screenshots")
    client = relationship("Client", back_populates="screenshots")

    @property
    def age_hours(self):
        """截图存在时间（小时）- 修复版"""
        if not self.screenshot_time:
            return 0

        from server_timezone import get_utc_now, make_naive

        now_naive = make_naive(get_utc_now())
        shot_naive = self._get_naive_screenshot_time()

        delta = now_naive - shot_naive
        return delta.total_seconds() / 3600

    def _get_naive_screenshot_time(self):
        """获取 naive 版本的 screenshot_time"""
        if not self.screenshot_time:
            return None
        if self.screenshot_time.tzinfo is not None:
            return self.screenshot_time.replace(tzinfo=None)
        return self.screenshot_time

    def to_dict(self):
        """转换为字典"""
        from server_timezone import format_beijing_time

        screenshot_time_beijing = None
        if self.screenshot_time:
            screenshot_time_beijing = to_beijing_time(self.screenshot_time)

        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "client_id": self.client_id,
            "filename": self.filename.split("/")[-1],
            "thumbnail": f"/screenshots/{self.thumbnail}" if self.thumbnail else None,
            "url": self.storage_url,
            "size": self.file_size,
            "size_str": self._format_size(self.file_size),
            "width": self.width,
            "height": self.height,
            "time": (
                screenshot_time_beijing.strftime("%H:%M:%S")
                if screenshot_time_beijing
                else None
            ),
            "date": (
                screenshot_time_beijing.strftime("%Y-%m-%d")
                if screenshot_time_beijing
                else None
            ),
            "datetime": (
                screenshot_time_beijing.strftime("%Y-%m-%d %H:%M:%S")
                if screenshot_time_beijing
                else None
            ),
            "computer_name": self.computer_name,
            "windows_user": self.windows_user,
            "format": self.image_format,
            "encrypted": self.is_encrypted,
            "age_hours": round(self.age_hours, 1),
        }

    @staticmethod
    def _format_size(size):
        for unit in ["B", "KB", "MB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}GB"


class Activity(Base):
    """活动日志表"""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        String(100),
        ForeignKey("employees.employee_id", ondelete="SET NULL"),
        index=True,
    )
    action = Column(String(50), nullable=False)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 关联
    employee = relationship("Employee", back_populates="activities")

    def to_dict(self):
        """转换为字典"""
        from server_timezone import format_beijing_time

        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "action": self.action,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": (
                format_beijing_time(self.created_at) if self.created_at else None
            ),
        }


# 系统设置表
class SystemConfig(Base):
    """系统配置表 - 存储所有动态配置"""

    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False)
    description = Column(String(200))
    category = Column(
        String(50), index=True
    )  # general, cleanup, storage, security, notification
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "category": self.category,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# server_models.py - 添加 Notification 模型


class Notification(Base):
    """通知表"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(200), nullable=False)
    content = Column(String(1000), nullable=True)
    type = Column(String(50), default="info")  # info, success, warning, error
    category = Column(String(50), default="system")  # system, client, cleanup, backup
    is_read = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # 关联字段
    related_id = Column(
        String(100), nullable=True
    )  # 关联的业务ID（如客户端ID、截图ID等）
    related_type = Column(String(50), nullable=True)  # 关联类型

    # 动作链接
    action_url = Column(String(500), nullable=True)
    action_text = Column(String(100), nullable=True)

    # 关联
    user = relationship("User")

    def to_dict(self):
        """转换为字典"""
        from server_timezone import format_beijing_time

        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "content": self.content,
            "type": self.type,
            "category": self.category,
            "is_read": self.is_read,
            "read": self.is_read,  # 兼容前端字段名
            "created_at": format_beijing_time(self.created_at),
            "read_at": format_beijing_time(self.read_at) if self.read_at else None,
            "related_id": self.related_id,
            "related_type": self.related_type,
            "action": (
                {"url": self.action_url, "text": self.action_text}
                if self.action_url
                else None
            ),
        }


# ==================== 浏览器历史记录表 ====================
class BrowserHistory(Base):
    """浏览器历史记录"""

    __tablename__ = "browser_history"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        String(100),
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id = Column(
        String(64), ForeignKey("clients.client_id", ondelete="SET NULL"), nullable=True
    )
    url = Column(String(5000), nullable=False)
    title = Column(String(2000))
    browser = Column(String(50))  # chrome, firefox, edge
    duration = Column(Integer, default=0)  # 停留时间（秒）
    visit_time = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联
    employee = relationship("Employee", backref="browser_history")
    client = relationship("Client", backref="browser_history")

    def to_dict(self):
        from server_timezone import format_beijing_time

        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "client_id": self.client_id,
            "url": self.url[:200] + "..." if len(self.url) > 200 else self.url,
            "full_url": self.url,
            "title": self.title,
            "browser": self.browser,
            "duration": self.duration,
            "duration_str": f"{self.duration//60}分{self.duration%60}秒",
            "visit_time": format_beijing_time(self.visit_time),
            "created_at": format_beijing_time(self.created_at),
        }


# ==================== 软件使用记录表 ====================
class AppUsage(Base):
    """软件使用记录"""

    __tablename__ = "app_usage"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        String(100),
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id = Column(
        String(64), ForeignKey("clients.client_id", ondelete="SET NULL"), nullable=True
    )
    app_name = Column(String(200), nullable=False)
    app_path = Column(String(500))
    window_title = Column(String(500))
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    duration = Column(Integer, default=0)  # 使用时长（秒）
    is_foreground = Column(Boolean, default=False)  # 是否前台应用
    cpu_avg = Column(Integer, default=0)  # 平均CPU使用率
    memory_avg = Column(Integer, default=0)  # 平均内存使用(MB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联
    employee = relationship("Employee", backref="app_usage")
    client = relationship("Client", backref="app_usage")

    def to_dict(self):
        from server_timezone import format_beijing_time

        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "client_id": self.client_id,
            "app_name": self.app_name,
            "app_path": self.app_path,
            "window_title": self.window_title,
            "start_time": format_beijing_time(self.start_time),
            "end_time": format_beijing_time(self.end_time) if self.end_time else None,
            "duration": self.duration,
            "duration_str": f"{self.duration//60}分{self.duration%60}秒",
            "is_foreground": self.is_foreground,
            "cpu_avg": self.cpu_avg,
            "memory_avg": self.memory_avg,
        }


# ==================== 文件操作记录表 ====================
class FileOperation(Base):
    """文件操作记录"""

    __tablename__ = "file_operations"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        String(100),
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id = Column(
        String(64), ForeignKey("clients.client_id", ondelete="SET NULL"), nullable=True
    )
    operation = Column(String(20), nullable=False)  # create, modify, delete, rename
    file_path = Column(String(1000), nullable=False)
    file_name = Column(String(500))
    file_size = Column(BigInteger, default=0)
    file_type = Column(String(50))  # 文件扩展名
    is_directory = Column(Boolean, default=False)
    operation_time = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联
    employee = relationship("Employee", backref="file_operations")
    client = relationship("Client", backref="file_operations")

    def to_dict(self):
        from server_timezone import format_beijing_time

        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "client_id": self.client_id,
            "operation": self.operation,
            "operation_cn": self._get_operation_cn(self.operation),
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_size_str": self._format_size(self.file_size),
            "file_type": self.file_type,
            "is_directory": self.is_directory,
            "operation_time": format_beijing_time(self.operation_time),
        }

    @staticmethod
    def _format_size(size):
        for unit in ["B", "KB", "MB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}GB"

    @staticmethod
    def _get_operation_cn(op):
        ops = {
            "create": "创建",
            "modify": "修改",
            "delete": "删除",
            "rename": "重命名",
            "move": "移动",
            "copy": "复制",
        }
        return ops.get(op, op)


# server_models.py - 在文件末尾添加


class CleanupPolicy(Base):
    """清理策略配置表"""

    __tablename__ = "cleanup_policies"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(50), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, default=True)
    retention_days = Column(Integer, nullable=True)  # 保留天数
    retention_hours = Column(Integer, nullable=True)  # 保留小时（截图专用）
    priority = Column(Integer, default=5)  # 优先级 1-10
    last_cleaned_at = Column(DateTime(timezone=True), nullable=True)
    cleaned_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "table_name": self.table_name,
            "enabled": self.enabled,
            "retention_days": self.retention_days,
            "retention_hours": self.retention_hours,
            "priority": self.priority,
            "last_cleaned_at": (
                self.last_cleaned_at.isoformat() if self.last_cleaned_at else None
            ),
            "cleaned_count": self.cleaned_count,
        }


# server_models.py - 添加以下内容到文件末尾


class Role(Base):
    """角色表"""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    description = Column(String(500))
    permissions = Column(JSON, default={"type": "none"})
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关联
    users = relationship("User", back_populates="role_rel")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "permissions": self.permissions,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Permission(Base):
    """权限表"""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), index=True)
    description = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ==================== 考勤管理模型 ====================


class AttendanceEmployee(Base):
    """考勤员工表"""

    __tablename__ = "attendance_employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    employee_id = Column(String(100), unique=True, nullable=False, index=True)
    hire_date = Column(DateTime(timezone=True), nullable=True)
    work_location = Column(String(50), default="现场")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    position = Column(String(100), nullable=True)

    # 关联
    attendance_records = relationship(
        "AttendanceRecord", back_populates="employee", cascade="all, delete-orphan"
    )
    performances = relationship(
        "Performance", back_populates="employee", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "employee_id": self.employee_id,
            "hire_date": (
                self.hire_date.strftime("%Y-%m-%d") if self.hire_date else None
            ),
            "work_location": self.work_location,
            "is_active": self.is_active,
            "position": self.position,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AttendanceRecord(Base):
    """考勤记录表"""

    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("attendance_employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    record_date = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), default="work")
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关联
    employee = relationship("AttendanceEmployee", back_populates="attendance_records")

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "record_date": (
                self.record_date.strftime("%Y-%m-%d") if self.record_date else None
            ),
            "status": self.status,
            "remark": self.remark,
        }


# server_models.py - 在 AttendanceRecord 模型之后添加

# server_models.py - 在 AttendanceRecord 模型之后添加


class Performance(Base):
    """绩效考核表"""

    __tablename__ = "performances"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("attendance_employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    month = Column(String(7), nullable=False, index=True)  # YYYY-MM
    total_score = Column(Integer, default=10)
    grade = Column(String(20), default="合格")
    score_records = Column(JSON, default=[])  # 加减分记录
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联
    employee = relationship("AttendanceEmployee", back_populates="performances")

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_name": self.employee.name if self.employee else None,
            "position": getattr(self.employee, "position", None),
            "month": self.month,
            "total_score": self.total_score,
            "grade": self.grade,
            "score_records": self.score_records or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PenaltyRecord(Base):
    """罚款记录表"""

    __tablename__ = "penalty_records"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("attendance_employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    penalty_date = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Integer, nullable=False)
    category = Column(String(50), nullable=False)
    reason = Column(String(500), nullable=False)
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关联
    employee = relationship("AttendanceEmployee", backref="penalty_records")

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "penalty_date": (
                self.penalty_date.strftime("%Y-%m-%d") if self.penalty_date else None
            ),
            "amount": self.amount,
            "category": self.category,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
