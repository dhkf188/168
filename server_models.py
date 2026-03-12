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
from server_timezone import get_utc_now, to_beijing_time, make_aware, BEIJING_TZ


class User(Base):
    """用户表（管理员）"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # admin, user
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "is_active": self.is_active,
        }


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
        """今日截图数量"""
        # 🚀 获取今天的开始和结束时间（UTC）
        from server_timezone import get_utc_now

        now_utc = get_utc_now()
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # 🚀 转换为 naive 用于数据库查询
        today_start_naive = today_start.replace(tzinfo=None)
        today_end_naive = today_end.replace(tzinfo=None)

        return sum(
            1
            for s in self.screenshots
            if today_start_naive <= s.screenshot_time < today_end_naive
        )

    @property
    def last_active(self):
        """最后活跃时间"""
        if not self.screenshots:
            return None
        # 🚀 返回 aware 时间
        last = max(s.screenshot_time for s in self.screenshots)
        return make_aware(last, BEIJING_TZ)

    @property
    def online_clients(self):
        """在线客户端数量"""
        # 🚀 使用 UTC 时间判断
        now_utc = get_utc_now()
        now_naive = now_utc.replace(tzinfo=None)

        count = 0
        for c in self.clients:
            if c.last_seen:
                if (now_naive - c.last_seen) < timedelta(minutes=10):
                    count += 1
        return count

    def to_dict(self):
        """增强的 to_dict 方法 - 统一版本"""
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
            "is_online": self.has_active_clients,
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
        """是否有活跃客户端（在线状态）"""
        if not self.clients:
            return False

        # 🚀 使用 UTC 时间判断
        from server_timezone import get_utc_now

        now_utc = get_utc_now()
        now_naive = now_utc.replace(tzinfo=None)

        for client in self.clients:
            if client.last_seen:
                # client.last_seen 是 naive UTC
                if (now_naive - client.last_seen) < timedelta(minutes=10):
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

    # ===== 修改这里：使用 lambda 函数从 Config 读取配置 =====

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
    # ====================================================

    capabilities = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联
    employee = relationship("Employee", back_populates="clients")
    screenshots = relationship("Screenshot", back_populates="client")

    @property
    def is_online(self):
        """是否在线"""
        if not self.last_seen:
            return False
        # 🚀 使用 UTC 时间判断
        now_utc = get_utc_now()
        now_naive = now_utc.replace(tzinfo=None)
        return (now_naive - self.last_seen) < timedelta(minutes=10)

    def to_dict(self):
        return {
            "client_id": self.client_id,
            "employee_id": self.employee_id,
            "computer_name": self.computer_name,
            "windows_user": self.windows_user,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "os_version": self.os_version,
            "client_version": self.client_version,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "is_online": self.is_online,
            "config": self.config,
            "capabilities": self.capabilities,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
        if self.screenshot_time:
            now = datetime.utcnow()
            # 确保两个时间都是 naive（无时区）
            if self.screenshot_time.tzinfo is not None:
                shot_time = self.screenshot_time.replace(tzinfo=None)
            else:
                shot_time = self.screenshot_time
            delta = now - shot_time
            return delta.total_seconds() / 3600
        return 0

    def to_dict(self):
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
            "time": self.screenshot_time.strftime("%H:%M:%S"),
            "date": self.screenshot_time.strftime("%Y-%m-%d"),
            "datetime": self.screenshot_time.strftime("%Y-%m-%d %H:%M:%S"),
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
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "action": self.action,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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
