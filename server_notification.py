# server_notification.py
"""
通知服务模块 - 管理所有系统通知
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

import server_models as models
import server_schemas as schemas
from server_timezone import get_utc_now, get_beijing_now, to_beijing_time

logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务类"""

    @staticmethod
    def create_notification(
        db: Session,
        user_id: int,
        title: str,
        content: Optional[str] = None,
        type: str = "info",
        category: str = "system",
        related_id: Optional[str] = None,
        related_type: Optional[str] = None,
        action_url: Optional[str] = None,
        action_text: Optional[str] = None,
        expires_hours: Optional[int] = None,
    ) -> models.Notification:
        """
        创建通知
        """
        now = get_utc_now()
        
        notification = models.Notification(
            user_id=user_id,
            title=title,
            content=content,
            type=type,
            category=category,
            related_id=related_id,
            related_type=related_type,
            action_url=action_url,
            action_text=action_text,
            created_at=now,
            expires_at=now + timedelta(hours=expires_hours) if expires_hours else None
        )
        
        db.add(notification)
        db.commit()
        db.refresh(notification)
        
        logger.info(f"✅ 通知已创建: {title} (用户ID: {user_id})")
        return notification

    @staticmethod
    def get_notifications(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        unread_first: bool = True,
        type: Optional[str] = None,
        category: Optional[str] = None,
        include_read: bool = True,
    ) -> Dict[str, Any]:
        """
        获取用户通知列表
        """
        query = db.query(models.Notification).filter(
            models.Notification.user_id == user_id,
            models.Notification.is_deleted == False
        )
        
        # 过滤已过期通知
        now = get_utc_now()
        query = query.filter(
            or_(
                models.Notification.expires_at.is_(None),
                models.Notification.expires_at > now
            )
        )
        
        # 按类型筛选
        if type:
            query = query.filter(models.Notification.type == type)
        
        # 按类别筛选
        if category:
            query = query.filter(models.Notification.category == category)
        
        # 是否包含已读
        if not include_read:
            query = query.filter(models.Notification.is_read == False)
        
        # 排序
        if unread_first:
            query = query.order_by(
                models.Notification.is_read.asc(),
                models.Notification.created_at.desc()
            )
        else:
            query = query.order_by(models.Notification.created_at.desc())
        
        # 总数
        total = query.count()
        
        # 分页
        notifications = query.offset(skip).limit(limit).all()
        
        # 检查是否还有更多
        has_more = (skip + len(notifications)) < total
        
        return {
            "items": [n.to_dict() for n in notifications],
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": has_more
        }

    @staticmethod
    def get_unread_count(db: Session, user_id: int) -> int:
        """
        获取用户未读通知数量
        """
        now = get_utc_now()
        return db.query(models.Notification).filter(
            models.Notification.user_id == user_id,
            models.Notification.is_read == False,
            models.Notification.is_deleted == False,
            or_(
                models.Notification.expires_at.is_(None),
                models.Notification.expires_at > now
            )
        ).count()

    @staticmethod
    def mark_as_read(db: Session, notification_id: int, user_id: int) -> bool:
        """
        标记通知为已读
        """
        notification = db.query(models.Notification).filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == user_id,
            models.Notification.is_deleted == False
        ).first()
        
        if not notification:
            return False
        
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = get_utc_now()
            db.commit()
            logger.debug(f"📖 通知已读: {notification_id}")
        
        return True

    @staticmethod
    def mark_all_as_read(db: Session, user_id: int) -> int:
        """
        标记用户所有通知为已读
        """
        now = get_utc_now()
        result = db.query(models.Notification).filter(
            models.Notification.user_id == user_id,
            models.Notification.is_read == False,
            models.Notification.is_deleted == False
        ).update({"is_read": True, "read_at": now})
        
        db.commit()
        logger.info(f"📚 全部已读: {result}条 (用户ID: {user_id})")
        return result

    @staticmethod
    def delete_notification(db: Session, notification_id: int, user_id: int) -> bool:
        """
        删除通知（软删除）
        """
        notification = db.query(models.Notification).filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == user_id
        ).first()
        
        if not notification:
            return False
        
        notification.is_deleted = True
        db.commit()
        logger.debug(f"🗑️ 通知已删除: {notification_id}")
        return True

    @staticmethod
    def clear_all(db: Session, user_id: int) -> int:
        """
        清空用户所有通知（软删除）
        """
        result = db.query(models.Notification).filter(
            models.Notification.user_id == user_id,
            models.Notification.is_deleted == False
        ).update({"is_deleted": True})
        
        db.commit()
        logger.info(f"🧹 清空通知: {result}条 (用户ID: {user_id})")
        return result

    @staticmethod
    def cleanup_expired(db: Session) -> int:
        """
        清理过期通知（定时任务调用）
        """
        now = get_utc_now()
        result = db.query(models.Notification).filter(
            models.Notification.expires_at.is_not(None),
            models.Notification.expires_at <= now,
            models.Notification.is_deleted == False
        ).update({"is_deleted": True})
        
        db.commit()
        if result > 0:
            logger.info(f"🧹 清理过期通知: {result}条")
        return result


# ==================== 系统自动通知创建函数 ====================

def notify_new_client_registered(db: Session, user_id: int, client_info: dict):
    """新客户端注册通知"""
    NotificationService.create_notification(
        db=db,
        user_id=user_id,
        title="新客户端注册",
        content=f"客户端 {client_info.get('computer_name', '未知')} 已成功注册",
        type="success",
        category="client",
        related_id=client_info.get('client_id'),
        related_type="client",
        action_url=f"/clients?client_id={client_info.get('client_id')}",
        action_text="查看客户端"
    )

def notify_storage_low(db: Session, user_id: int, usage_percent: float, free_gb: float):
    """存储空间不足通知"""
    NotificationService.create_notification(
        db=db,
        user_id=user_id,
        title="存储空间不足",
        content=f"已使用 {usage_percent:.1f}%，剩余 {free_gb:.1f}GB",
        type="error",
        category="system",
        action_url="/settings?tab=storage",
        action_text="清理存储",
        expires_hours=24
    )

def notify_cleanup_completed(db: Session, user_id: int, deleted_count: int, freed_mb: float):
    """清理完成通知"""
    NotificationService.create_notification(
        db=db,
        user_id=user_id,
        title="清理完成",
        content=f"已清理 {deleted_count} 个文件，释放 {freed_mb:.2f}MB 空间",
        type="success",
        category="cleanup",
        action_url="/settings?tab=cleanup",
        action_text="查看清理状态"
    )

def notify_backup_completed(db: Session, user_id: int, backup_info: dict):
    """备份完成通知"""
    NotificationService.create_notification(
        db=db,
        user_id=user_id,
        title="备份完成",
        content=f"数据库备份成功，大小: {backup_info.get('size_mb', 0)}MB",
        type="success",
        category="backup",
        action_url="/settings?tab=backup",
        action_text="查看备份"
    )

def notify_system_update(db: Session, user_id: int, version: str, changes: str):
    """系统更新通知"""
    NotificationService.create_notification(
        db=db,
        user_id=user_id,
        title="系统更新",
        content=f"系统已更新至版本 {version}\n更新内容: {changes}",
        type="info",
        category="system",
        expires_hours=72
    )