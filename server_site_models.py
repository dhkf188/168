# server_site_models.py
"""
站点数据管理模型 - 独立于现有员工表
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from server_database import Base


class Site(Base):
    """站点表"""

    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关联 - 使用字符串引用避免循环导入
    data_records = relationship(
        "SiteDataRecord", back_populates="site", cascade="all, delete-orphan"
    )
    accounts = relationship(
        "SiteEmployeeAccount", back_populates="site", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SiteEmployeeAccount(Base):
    """站点员工账号表 - 独立于现有员工表"""

    __tablename__ = "site_employee_accounts"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(100), nullable=False)
    account_name = Column(String(100), nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    shift = Column(String(10), default="day")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("site_id", "account_name", name="unique_site_account"),
    )

    # 关联
    site = relationship("Site", back_populates="accounts")
    data_records = relationship(
        "SiteDataRecord",
        back_populates="employee_account",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "site_id": self.site_id,
            "site_code": self.site.code if self.site else None,
            "site_name": self.site.name if self.site else None,
            "name": self.name,
            "account_name": self.account_name,
            "shift": self.shift,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SiteDataRecord(Base):
    """站点数据记录表"""

    __tablename__ = "site_data_records"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    site_code = Column(String(20), nullable=True, index=True)
    employee_account_id = Column(
        Integer,
        ForeignKey("site_employee_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    account_name = Column(String(100), nullable=True, index=True)
    shift = Column(String(10), default="day", index=True)
    date = Column(DateTime, nullable=False, index=True)
    value = Column(Integer, default=0)
    avg_time_seconds = Column(Integer, default=0)
    avg_time_str = Column(String(20))
    raw_data = Column(JSON, nullable=True)
    batch_id = Column(String(50), index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关联 - 正确的定义
    site = relationship("Site", back_populates="data_records")
    employee_account = relationship(
        "SiteEmployeeAccount", back_populates="data_records"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "site_id": self.site_id,
            "site_code": self.site_code or (self.site.code if self.site else None),
            "site_name": self.site.name if self.site else None,
            "employee_account_id": self.employee_account_id,
            "employee_name": (
                self.employee_account.name if self.employee_account else None
            ),
            "account_name": self.account_name,
            "shift": self.shift,
            "date": self.date.isoformat() if self.date else None,
            "value": self.value,
            "avg_time_seconds": self.avg_time_seconds,
            "avg_time_str": self.avg_time_str,
            "batch_id": self.batch_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UploadBatch(Base):
    """上传批次表"""

    __tablename__ = "upload_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), unique=True, nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)
    filename = Column(String(255))
    file_type = Column(String(20))
    record_count = Column(Integer, default=0)
    matched_count = Column(Integer, default=0)
    unmatched_count = Column(Integer, default=0)
    status = Column(String(20), default="processing")
    error_message = Column(Text, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "site_id": self.site_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "record_count": self.record_count,
            "matched_count": self.matched_count,
            "unmatched_count": self.unmatched_count,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
