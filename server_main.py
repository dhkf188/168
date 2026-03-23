from fastapi import (
    FastAPI,
    File,
    UploadFile,
    Form,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
from pathlib import Path
import shutil
import os
import sys
import uuid
import logging
import asyncio
import json
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from pydantic import BaseModel
from sqlalchemy import exists, and_, or_, select
from sqlalchemy.orm import selectinload
import mimetypes
from pathlib import Path
from server_remote_screen import router as remote_screen_router
from server_remote_screen import session_manager

import server_models as models
import server_schemas as schemas
from server_database import engine, get_db, get_backup_db
from server_auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_current_active_user,
    get_current_admin_user,
    verify_password,
)
from server_cleanup import DataCleanup
from server_config import Config
from server_timezone import (
    get_utc_now,
    get_beijing_now,
    to_beijing_time,
    to_utc_time,
    make_naive,
    make_aware,
    format_beijing_time,
    get_date_range_for_day,
    parse_beijing_datetime,
    BEIJING_TZ,
    UTC,
)
from server_notification import NotificationService
import server_schemas as schemas

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建数据库表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="员工监控系统 API",
    description="企业级员工行为监控系统",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 创建存储目录
STORAGE_PATH = Path(Config.SCREENSHOT_DIR)
STORAGE_PATH.mkdir(parents=True, exist_ok=True)
logger.info(f"✅ 截图存储路径: {STORAGE_PATH.absolute()}")

THUMBNAIL_PATH = STORAGE_PATH / "thumbnails"
THUMBNAIL_PATH.mkdir(parents=True, exist_ok=True)
logger.info(f"✅ 缩略图存储路径: {THUMBNAIL_PATH.absolute()}")


# 列出一些文件用于调试
try:
    files = list(STORAGE_PATH.glob("**/*.webp"))[:5]
    if files:
        logger.info(
            f"📸 找到示例截图: {[str(f.relative_to(STORAGE_PATH)) for f in files]}"
        )
except Exception as e:
    logger.error(f"❌ 读取截图目录失败: {e}")

# 启动清理任务
cleanup = DataCleanup()


@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化 - 增强版文件系统检查"""
    logger.info("=" * 50)
    logger.info("🚀 员工监控系统服务器启动")
    logger.info("=" * 50)

    # ===== 🚨 自动迁移旧截图目录（优化版） =====
    try:
        import shutil
        from pathlib import Path

        target_path = STORAGE_PATH.absolute()
        logger.info(f"📁 目标存储路径: {target_path}")
        target_path.mkdir(parents=True, exist_ok=True)

        # 所有可能的旧路径
        possible_old_paths = [
            Path("./screenshots").absolute(),
            Path("/app/screenshots").absolute(),
            Path("/var/lib/screenshots").absolute(),
            Path("/tmp/screenshots").absolute(),
            Path.cwd() / "screenshots",
            Path("/opt/render/project/src/screenshots"),
        ]

        # 去重并过滤
        unique_old_paths = []
        seen = set()
        for p in possible_old_paths:
            p_str = str(p)
            if p_str not in seen and p != target_path:
                seen.add(p_str)
                unique_old_paths.append(p)

        logger.info("📁 检查是否需要迁移旧截图目录...")

        total_migrated = 0
        total_files = 0
        total_size = 0

        for old_path in unique_old_paths:
            if old_path.exists() and old_path.is_dir():
                logger.info(f"   发现旧目录: {old_path}")

                # 优化：只扫描一次获取所有图片文件
                all_files = []
                for f in old_path.rglob("*"):
                    if f.is_file() and f.suffix.lower() in [".webp", ".jpg", ".png"]:
                        all_files.append(f)

                if all_files:
                    file_count = len(all_files)
                    dir_size = sum(f.stat().st_size for f in all_files)

                    logger.info(
                        f"     找到 {file_count} 个截图文件，总大小: {dir_size/1024/1024:.2f} MB"
                    )

                    # 迁移每个文件
                    for file_path in all_files:
                        try:
                            rel_path = file_path.relative_to(old_path)
                            target_file = target_path / rel_path

                            target_file.parent.mkdir(parents=True, exist_ok=True)

                            if target_file.exists():
                                logger.debug(f"     文件已存在，跳过: {rel_path}")
                                continue

                            # 先获取大小再移动
                            file_size = file_path.stat().st_size
                            shutil.move(str(file_path), str(target_file))

                            total_files += 1
                            total_size += file_size
                            logger.debug(
                                f"     已迁移: {rel_path} ({file_size/1024:.1f}KB)"
                            )

                        except Exception as e:
                            logger.error(f"     迁移文件失败 {file_path}: {e}")

                    total_migrated += 1

                    # 优化：快速检查目录是否为空
                    try:
                        if not any(old_path.iterdir()):
                            old_path.rmdir()
                            logger.info(f"     已删除空目录: {old_path}")
                    except Exception as e:
                        logger.debug(f"     无法删除目录 {old_path}: {e}")

        if total_migrated > 0:
            logger.info(f"✅ 迁移完成！")
            logger.info(f"   迁移了 {total_migrated} 个旧目录")
            logger.info(
                f"   共 {total_files} 个文件，总大小: {total_size/1024/1024:.2f} MB"
            )
            logger.info(f"   所有文件已移至: {target_path}")
        else:
            logger.info("未找到需要迁移的旧截图目录")

    except Exception as e:
        logger.error(f"❌ 截图目录迁移失败: {e}", exc_info=True)

    # ===== 1. 数据库信息 =====
    logger.info("📊 数据库配置:")
    db_url_display = Config.PRIMARY_DATABASE_URL
    if "@" in db_url_display:
        parts = db_url_display.split("@")
        auth_part = parts[0].split(":")
        if len(auth_part) > 2:
            db_url_display = f"{auth_part[0]}:****@{parts[1]}"
    logger.info(f"   - 主数据库: {db_url_display}")
    logger.info(f"   - 存储路径: {STORAGE_PATH}")
    logger.info(
        f"   - 自动清理: {'✅ 启用' if Config.AUTO_CLEANUP_ENABLED else '❌ 禁用'}"
    )
    logger.info(f"   - 数据保留: {Config.SCREENSHOT_RETENTION_HOURS}小时")
    logger.info(f"   - 清理间隔: {Config.CLEANUP_INTERVAL/3600:.1f}小时")

    # ===== 2. 启动清理任务 =====
    logger.info("=" * 50)
    logger.info("🧹 启动清理任务...")
    asyncio.create_task(cleanup.start_cleanup_task())
    logger.info("✅ 清理任务已启动")

    logger.info("=" * 50)
    logger.info("🖥️ 启动远程屏幕服务...")
    from server_remote_screen import start_remote_service

    await start_remote_service()
    logger.info("✅ 远程屏幕服务已启动")

    # ===== 3. 文件系统检查（优化版） =====
    logger.info("=" * 50)
    logger.info("📁 文件系统检查:")

    # 3.1 检查存储路径
    logger.info(f"   存储路径: {STORAGE_PATH}")
    if STORAGE_PATH.exists():
        logger.info(f"   ✅ 存储路径存在")

        # 检查权限
        try:
            test_file = STORAGE_PATH / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            logger.info(f"   ✅ 存储路径可写")
        except Exception as e:
            logger.error(f"   ❌ 存储路径不可写: {e}")

        # 优化：只统计图片文件
        try:
            webp_files = []
            jpg_files = []
            png_files = []
            total_size = 0

            for f in STORAGE_PATH.rglob("*"):
                if f.is_file():
                    suffix = f.suffix.lower()
                    if suffix == ".webp":
                        webp_files.append(f)
                        total_size += f.stat().st_size
                    elif suffix == ".jpg":
                        jpg_files.append(f)
                        total_size += f.stat().st_size
                    elif suffix == ".png":
                        png_files.append(f)
                        total_size += f.stat().st_size

            total_files = len(webp_files) + len(jpg_files) + len(png_files)

            logger.info(f"   📊 文件统计:")
            logger.info(f"      - 总文件数: {total_files} 个")
            logger.info(f"      - WebP文件: {len(webp_files)} 个")
            logger.info(f"      - JPG文件: {len(jpg_files)} 个")
            logger.info(f"      - PNG文件: {len(png_files)} 个")
            logger.info(f"      - 总大小: {total_size / (1024*1024):.2f} MB")

            # 显示前3个示例文件
            if webp_files:
                logger.info(f"   📸 示例截图 (WebP):")
                for i, f in enumerate(webp_files[:3]):
                    rel_path = f.relative_to(STORAGE_PATH)
                    size_kb = f.stat().st_size / 1024
                    logger.info(f"      {i+1}. {rel_path} ({size_kb:.1f}KB)")

            # 检查员工目录结构
            employee_dirs = [d for d in STORAGE_PATH.iterdir() if d.is_dir()]
            logger.info(f"   👥 员工目录数: {len(employee_dirs)}")
            if employee_dirs:
                logger.info(f"      示例: {[d.name for d in employee_dirs[:5]]}")

        except Exception as e:
            logger.error(f"   ❌ 统计文件失败: {e}")
    else:
        logger.error(f"   ❌ 存储路径不存在!")
        logger.info(f"   尝试创建目录...")
        try:
            STORAGE_PATH.mkdir(parents=True, exist_ok=True)
            logger.info(f"   ✅ 存储路径创建成功")
        except Exception as e:
            logger.error(f"   ❌ 创建存储路径失败: {e}")

    # 3.2 检查缩略图目录
    logger.info(f"   缩略图路径: {THUMBNAIL_PATH}")
    if THUMBNAIL_PATH.exists():
        # 优化：只统计图片文件
        thumb_files = []
        for f in THUMBNAIL_PATH.rglob("*"):
            if f.is_file() and f.suffix.lower() == ".webp":
                thumb_files.append(f)
        logger.info(f"   ✅ 缩略图目录存在 ({len(thumb_files)} 个文件)")
    else:
        logger.info(f"   ⚠️ 缩略图目录不存在，将自动创建")
        try:
            THUMBNAIL_PATH.mkdir(parents=True, exist_ok=True)
            logger.info(f"   ✅ 缩略图目录创建成功")
        except Exception as e:
            logger.error(f"   ❌ 创建缩略图目录失败: {e}")

    # 3.3 检查磁盘空间（保持不变）
    try:
        import shutil

        disk_usage = shutil.disk_usage(STORAGE_PATH)
        free_gb = disk_usage.free / (1024**3)
        total_gb = disk_usage.total / (1024**3)
        used_percent = (disk_usage.used / disk_usage.total) * 100

        logger.info(f"   💾 磁盘空间:")
        logger.info(f"      - 总空间: {total_gb:.1f} GB")
        logger.info(f"      - 已用: {used_percent:.1f}%")
        logger.info(f"      - 剩余: {free_gb:.1f} GB")

        if free_gb < 5:
            logger.warning(f"   ⚠️ 磁盘空间不足! 剩余 {free_gb:.1f}GB")
        else:
            logger.info(f"   ✅ 磁盘空间充足")
    except Exception as e:
        logger.error(f"   ❌ 检查磁盘空间失败: {e}")

    # ===== 4. 创建默认管理员（修复 Session 问题） =====
    logger.info("=" * 50)
    logger.info("👤 管理员账户检查:")

    # ✅ 修复：使用 get_db 但确保正确关闭
    db = None
    try:
        # 使用原有的 get_db 生成器
        db = next(get_db())

        admin = (
            db.query(models.User)
            .filter(models.User.username == Config.ADMIN_USERNAME)
            .first()
        )

        if not admin:
            admin = models.User(
                username=Config.ADMIN_USERNAME,
                password_hash=get_password_hash(Config.ADMIN_PASSWORD),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info(f"   ✅ 默认管理员已创建: {Config.ADMIN_USERNAME}")
        else:
            logger.info(f"   ✅ 管理员用户已存在: {Config.ADMIN_USERNAME}")

        # 统计用户数量
        user_count = db.query(models.User).count()
        logger.info(f"   👥 系统用户数: {user_count}")

    except Exception as e:
        logger.error(f"   ❌ 管理员检查失败: {e}")
    finally:
        if db:
            db.close()

    # ===== 5. 数据库表统计（修复 Session 问题） =====
    logger.info("=" * 50)
    logger.info("📊 数据库统计:")

    db = None
    try:
        db = next(get_db())

        screenshot_count = db.query(models.Screenshot).count()
        employee_count = db.query(models.Employee).count()
        client_count = db.query(models.Client).count()
        activity_count = db.query(models.Activity).count()

        logger.info(f"   📸 截图数: {screenshot_count}")
        logger.info(f"   👤 员工数: {employee_count}")
        logger.info(f"   💻 客户端数: {client_count}")
        logger.info(f"   📝 活动日志: {activity_count}")

        if activity_count > 0:
            latest_activity = (
                db.query(models.Activity)
                .order_by(models.Activity.created_at.desc())
                .first()
            )
            logger.info(
                f"   ⏱️ 最近活动: {latest_activity.action} ({latest_activity.created_at})"
            )

    except Exception as e:
        logger.error(f"   ❌ 数据库统计失败: {e}")
    finally:
        if db:
            db.close()

    # ===== 6. 环境信息 =====
    logger.info("=" * 50)
    logger.info("🌍 环境信息:")
    logger.info(f"   - Python版本: {sys.version}")
    logger.info(f"   - 当前目录: {os.getcwd()}")
    logger.info(f"   - 调试模式: {Config.DEBUG}")
    logger.info(f"   - 日志级别: {Config.LOG_LEVEL}")

    # 检查环境变量
    important_envs = ["DATABASE_URL", "REDIS_URL", "SECRET_KEY"]
    for env in important_envs:
        value = os.environ.get(env, "未设置")
        if env == "SECRET_KEY" and value != "未设置":
            value = "已设置(隐藏)"
        logger.info(f"   - {env}: {value}")

    # ===== ⭐ 新增：验证StaticFiles =====
    logger.info("=" * 50)
    logger.info("🔍 验证StaticFiles可访问性:")

    try:
        db = next(get_db())
        # 获取第100页的截图（只是为了测试）
        test_screenshots = (
            db.query(models.Screenshot)
            .order_by(models.Screenshot.screenshot_time.desc())
            .offset(100 * 24)
            .limit(3)
            .all()
        )

        if test_screenshots:
            logger.info(f"找到 {len(test_screenshots)} 个第100页后的截图:")
            for ss in test_screenshots:
                file_path = screenshots_path / ss.filename
                logger.info(f"  - ID: {ss.id}")
                logger.info(f"    时间: {ss.screenshot_time}")
                logger.info(f"    文件: {file_path}")
                logger.info(f"    存在: {file_path.exists()}")
                logger.info(f"    URL: {ss.storage_url}")
        else:
            logger.info("没有第100页后的截图数据")

        db.close()
    except Exception as e:
        logger.error(f"验证失败: {e}")

    logger.info("=" * 50)

    logger.info("=" * 50)
    logger.info("✅ 服务器启动完成!")
    logger.info("=" * 50)

    # ===== 7. 创建通知表（如果不存在）和示例通知 =====
    logger.info("=" * 50)
    logger.info("📨 通知系统初始化:")

    db = None
    try:
        db = next(get_db())

        # 检查通知表是否存在，如果不存在则创建
        from sqlalchemy import inspect

        inspector = inspect(db.bind)
        if "notifications" not in inspector.get_table_names():
            logger.info("   📋 创建通知表...")
            # 这里不需要手动创建表，SQLAlchemy 会在启动时自动创建
            # 但我们可以记录一下
            logger.info("   ✅ 通知表将由 SQLAlchemy 自动创建")

        # 统计通知数量
        notification_count = db.query(models.Notification).count()
        logger.info(f"   📊 现有通知数: {notification_count}")

        # 只在调试模式和没有通知时创建示例通知
        if notification_count == 0 and Config.DEBUG:
            logger.info("   ✨ 创建示例通知...")

            # 获取管理员用户
            admin = (
                db.query(models.User)
                .filter(models.User.username == Config.ADMIN_USERNAME)
                .first()
            )

            if admin:
                from server_notification import NotificationService

                # 欢迎通知
                NotificationService.create_notification(
                    db=db,
                    user_id=admin.id,
                    title="欢迎使用监控系统",
                    content="感谢您使用员工监控系统，所有功能已就绪",
                    type="info",
                    category="system",
                )

                # 系统状态通知
                NotificationService.create_notification(
                    db=db,
                    user_id=admin.id,
                    title="系统状态正常",
                    content=f"存储路径: {STORAGE_PATH}\n自动清理: {'已启用' if Config.AUTO_CLEANUP_ENABLED else '已禁用'}",
                    type="success",
                    category="system",
                )

                # 示例客户端注册通知
                NotificationService.create_notification(
                    db=db,
                    user_id=admin.id,
                    title="新客户端注册示例",
                    content="当有新客户端注册时，您会在这里收到通知",
                    type="info",
                    category="client",
                    action_url="/clients",
                    action_text="查看客户端",
                )

                logger.info(f"   ✅ 已创建 3 条示例通知")
            else:
                logger.warning("   ⚠️ 未找到管理员用户，跳过示例通知创建")

        # 清理过期通知（每天启动时清理一次）
        if notification_count > 0:
            from server_notification import NotificationService

            expired_count = NotificationService.cleanup_expired(db)
            if expired_count > 0:
                logger.info(f"   🧹 已清理 {expired_count} 条过期通知")

    except Exception as e:
        logger.error(f"   ❌ 通知系统初始化失败: {e}")
        logger.debug(f"      错误详情: {str(e)}")
    finally:
        if db:
            db.close()
            logger.info("   ✅ 数据库连接已关闭")

    logger.info("=" * 50)
    logger.info("✅ 服务器启动完成!")
    logger.info("=" * 50)


# ==================== 健康检查 ====================
@app.get("/health", tags=["系统"])
async def health_check():
    """系统健康检查"""
    health_status = {
        "status": "healthy",
        "timestamp": get_beijing_now().isoformat(),
        "version": "3.0.0",
        "auto_cleanup": {
            "enabled": Config.AUTO_CLEANUP_ENABLED,
            "interval_hours": Config.CLEANUP_INTERVAL / 3600,
            "retention_hours": Config.SCREENSHOT_RETENTION_HOURS,
        },
        "image_config": {
            "format": Config.SCREENSHOT_FORMAT,
            "quality": Config.SCREENSHOT_QUALITY,
        },
    }

    # 导入 text
    from sqlalchemy import text

    # 检查主数据库
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))  # ✅ 修改：用 text() 包裹
        db.close()
        health_status["database"] = "healthy"
    except Exception as e:
        health_status["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # 检查备用数据库（如果配置了）
    if Config.BACKUP_DATABASE_URL:
        try:
            backup_db = next(get_backup_db())
            backup_db.execute(text("SELECT 1"))  # ✅ 修改：用 text() 包裹
            backup_db.close()
            health_status["backup_database"] = "healthy"
        except Exception as e:
            health_status["backup_database"] = f"unhealthy: {str(e)}"

    return health_status


# ==================== 系统设置接口 ====================


class GeneralConfigSchema(BaseModel):
    system_name: str
    default_interval: int
    default_format: str
    default_quality: int
    timezone: str


class CleanupConfigSchema(BaseModel):
    enabled: bool
    retention_hours: int
    interval_hours: int
    cleanup_time: Optional[str] = None


class StorageConfigSchema(BaseModel):
    path: str
    max_size_gb: int
    thumbnail_size: int
    thumbnail_quality: int


class SecurityConfigSchema(BaseModel):
    jwt_expire_minutes: int


class NotificationConfigSchema(BaseModel):
    enabled: bool
    methods: List[str]
    smtp_server: Optional[str] = None
    from_email: Optional[str] = None
    to_email: Optional[str] = None
    events: dict


class BackupConfigSchema(BaseModel):
    enabled: bool
    frequency: str
    backup_time: Optional[str] = None
    keep_count: int


@app.get("/api/settings/all", tags=["系统设置"])
def get_all_settings(
    current_user: models.User = Depends(get_current_active_user),
):
    """获取所有系统设置"""
    from server_config_manager import get_config

    return {
        "general": {
            "system_name": get_config("system_name", "员工监控系统"),
            "default_interval": get_config("screenshot_interval", 60),
            "default_format": get_config("screenshot_format", "webp"),
            "default_quality": get_config("screenshot_quality", 80),
            "timezone": get_config("timezone", "Asia/Shanghai"),
        },
        "cleanup": {
            "enabled": get_config("auto_cleanup_enabled", True),
            "retention_hours": get_config("screenshot_retention_hours", 4),
            "interval_hours": get_config("cleanup_interval", 21600) / 3600,
            "cleanup_time": get_config("cleanup_time", None),
        },
        "storage": {
            "path": get_config("screenshot_dir", "/data/screenshots"),
            "max_size_gb": get_config("max_storage_gb", 100),
            "thumbnail_size": get_config("thumbnail_size", 320),
            "thumbnail_quality": get_config("thumbnail_quality", 75),
        },
        "security": {
            "jwt_expire_minutes": get_config("jwt_expire_minutes", 480),
        },
        "backup": {
            "enabled": get_config("backup_enabled", True),
            "frequency": get_config("backup_frequency", "daily"),
            "backup_time": get_config("backup_time", None),
            "keep_count": get_config("backup_keep_count", 7),
        },
        "notification": {
            "enabled": get_config("notification_enabled", True),
            "methods": get_config("notification_methods", ["email"]),
            "smtp_server": get_config("smtp_server", ""),
            "from_email": get_config("from_email", ""),
            "to_email": get_config("to_email", ""),
            "events": get_config(
                "notification_events",
                {
                    "clientRegister": True,
                    "clientOffline": True,
                    "lowStorage": True,
                    "backupComplete": True,
                },
            ),
        },
    }


@app.post("/api/settings/general", tags=["系统设置"])
def update_general_settings(
    config: GeneralConfigSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """更新通用设置"""
    from server_config_manager import set_config

    set_config(
        "system_name", config.system_name, "general", "系统名称", current_user.id
    )
    set_config(
        "screenshot_interval",
        config.default_interval,
        "general",
        "默认截图间隔",
        current_user.id,
    )
    set_config(
        "screenshot_format",
        config.default_format,
        "general",
        "默认图片格式",
        current_user.id,
    )
    set_config(
        "screenshot_quality",
        config.default_quality,
        "general",
        "默认图片质量",
        current_user.id,
    )
    set_config("timezone", config.timezone, "general", "时区", current_user.id)

    logger.info(f"通用设置已更新: {config.dict()} 更新者: {current_user.username}")
    return {"message": "通用设置已保存"}


@app.post("/api/settings/cleanup", tags=["系统设置"])
def update_cleanup_settings(
    config: CleanupConfigSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """更新清理策略"""
    from server_config_manager import set_config

    set_config(
        "auto_cleanup_enabled",
        config.enabled,
        "cleanup",
        "自动清理开关",
        current_user.id,
    )
    set_config(
        "screenshot_retention_hours",
        config.retention_hours,
        "cleanup",
        "截图保留时间",
        current_user.id,
    )
    set_config(
        "cleanup_interval",
        int(config.interval_hours * 3600),
        "cleanup",
        "清理间隔",
        current_user.id,
    )
    if config.cleanup_time:
        set_config(
            "cleanup_time", config.cleanup_time, "cleanup", "清理时间", current_user.id
        )

    logger.info(f"清理策略已更新: {config.dict()} 更新者: {current_user.username}")
    return {"message": "清理策略已保存"}


@app.post("/api/settings/storage", tags=["系统设置"])
def update_storage_settings(
    config: StorageConfigSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """更新存储设置"""
    from server_config_manager import set_config

    set_config("screenshot_dir", config.path, "storage", "存储路径", current_user.id)
    set_config(
        "max_storage_gb", config.max_size_gb, "storage", "最大存储空间", current_user.id
    )
    set_config(
        "thumbnail_size",
        config.thumbnail_size,
        "storage",
        "缩略图大小",
        current_user.id,
    )
    set_config(
        "thumbnail_quality",
        config.thumbnail_quality,
        "storage",
        "缩略图质量",
        current_user.id,
    )

    logger.info(f"存储设置已更新: {config.dict()} 更新者: {current_user.username}")
    return {"message": "存储设置已保存"}


@app.post("/api/settings/security", tags=["系统设置"])
def update_security_settings(
    config: SecurityConfigSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """更新安全设置"""
    from server_config_manager import set_config

    set_config(
        "jwt_expire_minutes",
        config.jwt_expire_minutes,
        "security",
        "JWT过期时间",
        current_user.id,
    )

    logger.info(f"安全设置已更新: {config.dict()} 更新者: {current_user.username}")
    return {"message": "安全设置已保存"}


@app.post("/api/settings/backup", tags=["系统设置"])
def update_backup_settings(
    config: BackupConfigSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """更新备份设置"""
    from server_config_manager import set_config

    set_config(
        "backup_enabled", config.enabled, "backup", "自动备份开关", current_user.id
    )
    set_config(
        "backup_frequency", config.frequency, "backup", "备份频率", current_user.id
    )
    if config.backup_time:
        set_config(
            "backup_time", config.backup_time, "backup", "备份时间", current_user.id
        )
    set_config(
        "backup_keep_count", config.keep_count, "backup", "保留备份数", current_user.id
    )

    logger.info(f"备份设置已更新: {config.dict()} 更新者: {current_user.username}")
    return {"message": "备份设置已保存"}


@app.post("/api/settings/notification", tags=["系统设置"])
def update_notification_settings(
    config: NotificationConfigSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """更新通知设置"""
    from server_config_manager import set_config

    set_config(
        "notification_enabled",
        config.enabled,
        "notification",
        "通知开关",
        current_user.id,
    )
    set_config(
        "notification_methods",
        config.methods,
        "notification",
        "通知方式",
        current_user.id,
    )
    set_config(
        "smtp_server", config.smtp_server, "notification", "邮件服务器", current_user.id
    )
    set_config(
        "from_email", config.from_email, "notification", "发件人邮箱", current_user.id
    )
    set_config("to_email", config.to_email, "notification", "接收邮箱", current_user.id)
    set_config(
        "notification_events",
        config.events,
        "notification",
        "通知事件",
        current_user.id,
    )

    logger.info(f"通知设置已更新: {config.dict()} 更新者: {current_user.username}")
    return {"message": "通知设置已保存"}


# ==================== 认证接口 ====================


@app.post("/api/auth/register", response_model=schemas.User, tags=["认证"])
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """注册新用户"""
    db_user = (
        db.query(models.User).filter(models.User.username == user.username).first()
    )

    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在"
        )

    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username, password_hash=hashed_password, role=user.role or "user"
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    logger.info(f"新用户注册: {user.username}")
    return db_user


@app.post("/api/auth/login", response_model=schemas.Token, tags=["认证"])
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """用户登录"""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires,
    )

    logger.info(f"用户登录: {user.username}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@app.get("/api/auth/me", response_model=schemas.User, tags=["认证"])
async def get_current_user_info(
    current_user: models.User = Depends(get_current_active_user),
):
    """获取当前用户信息"""
    return current_user


# ==================== 客户端接口 ====================
@app.post("/api/client/register", response_model=schemas.Client, tags=["客户端"])
async def register_client(
    client_info: schemas.ClientCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """客户端注册 - 强隔离优化版"""
    beijing_now = get_beijing_now()
    logger.info("=" * 50)
    logger.info(
        f"📝 收到注册请求: {client_info.computer_name} ({client_info.windows_user})"
    )

    employee_name = getattr(client_info, "employee_name", None)

    # ===== 1. 优化后的查找优先级 =====
    existing_client = None
    client_found_by = None

    # 优先级顺序：硬件指纹 > MAC地址 > 硬盘序列号 > client_id
    search_priorities = [
        ("hardware_fingerprint", client_info.hardware_fingerprint),  # 最精确
        ("mac_address", client_info.mac_address),  # 稳定
        ("disk_serial", client_info.disk_serial),  # 较稳定
        ("client_id", client_info.client_id),  # 最后考虑
    ]

    for field_name, value in search_priorities:
        if value:
            existing_client = (
                db.query(models.Client)
                .filter(getattr(models.Client, field_name) == value)
                .first()
            )
            if existing_client:
                client_found_by = field_name
                break

    # CPU+MAC组合查找（备用）
    if not existing_client and client_info.cpu_id and client_info.mac_address:
        existing_client = (
            db.query(models.Client)
            .filter(
                models.Client.cpu_id == client_info.cpu_id,
                models.Client.mac_address == client_info.mac_address,
            )
            .first()
        )
        if existing_client:
            client_found_by = "cpu_mac_combo"

    # ===== 2. 增强的防碰撞逻辑 =====
    if existing_client:
        # 核心防碰撞：硬件指纹不同则强制新建
        hardware_conflict = (
            existing_client.hardware_fingerprint
            and client_info.hardware_fingerprint
            and existing_client.hardware_fingerprint != client_info.hardware_fingerprint
        )

        if hardware_conflict:
            logger.warning(
                f"🚨 硬件指纹冲突！"
                f"旧: {existing_client.hardware_fingerprint[:16]}... "
                f"新: {client_info.hardware_fingerprint[:16]}... "
                f"将创建新记录"
            )
            existing_client = None
        else:
            logger.info(f"✅ 客户端回连: [{client_found_by}] 匹配成功")

            # 如果是通过非硬件指纹找到的，但新请求有硬件指纹，则补充
            if (
                client_found_by != "hardware_fingerprint"
                and client_info.hardware_fingerprint
            ):
                if not existing_client.hardware_fingerprint:
                    logger.info(f"📌 补充硬件指纹到现有客户端")
                    existing_client.hardware_fingerprint = (
                        client_info.hardware_fingerprint
                    )
                    existing_client.hardware_parts = client_info.hardware_parts
                    existing_client.has_hardware = client_info.has_hardware

    # ===== 3. 优化更新逻辑 =====
    if existing_client:
        # 保留原始ID
        original_client_id = existing_client.client_id

        # 只更新必要字段
        update_fields = [
            "computer_name",
            "windows_user",
            "ip_address",
            "os_version",
            "client_version",
        ]

        for field in update_fields:
            new_value = getattr(client_info, field, None)
            if new_value is not None:
                setattr(existing_client, field, new_value)

        existing_client.last_seen = beijing_now
        existing_client.client_id = original_client_id

        # 智能更新员工姓名
        if employee_name and existing_client.employee_id:
            emp = (
                db.query(models.Employee)
                .filter(models.Employee.employee_id == existing_client.employee_id)
                .first()
            )
            if emp and (not emp.name or emp.name.startswith(emp.computer_name or "")):
                emp.name = employee_name
                logger.info(f"📝 更新员工姓名: {emp.name}")

        db.commit()
        db.refresh(existing_client)
        return existing_client

    # ===== 4. 优化创建新记录 =====
    import uuid
    import hashlib

    # 生成唯一后缀
    if client_info.hardware_fingerprint:
        unique_suffix = client_info.hardware_fingerprint[:12]
        logger.info(f"🔐 基于硬件指纹生成ID: {unique_suffix}")
    else:
        # 无硬件指纹时，基于多信息生成
        unique_str = f"{client_info.mac_address or ''}{client_info.computer_name or ''}{uuid.uuid4()}"
        unique_suffix = hashlib.md5(unique_str.encode()).hexdigest()[:12]
        logger.warning(f"⚠️ 无硬件指纹，生成临时ID: {unique_suffix}")

    # 构造员工ID
    computer = client_info.computer_name or "PC"
    user = client_info.windows_user or "USER"
    employee_id = f"{computer}\\{user}_{unique_suffix}"

    # 检查冲突
    if (
        db.query(models.Employee)
        .filter(models.Employee.employee_id == employee_id)
        .first()
    ):
        employee_id = f"{employee_id}_{uuid.uuid4().hex[:4]}"
        logger.warning(f"⚠️ ID冲突，重新生成: {employee_id}")

    # 创建员工
    employee = models.Employee(
        employee_id=employee_id,
        name=employee_name or f"员工_{unique_suffix[:6]}",
        computer_name=client_info.computer_name,
        windows_user=client_info.windows_user,
        department="自动注册",
        status="active",
        created_at=beijing_now,
    )
    db.add(employee)

    # 创建客户端
    client_id = client_info.client_id or f"client_{unique_suffix}"
    if db.query(models.Client).filter(models.Client.client_id == client_id).first():
        client_id = f"client_{unique_suffix}_{uuid.uuid4().hex[:4]}"

    new_client = models.Client(
        client_id=client_id,
        employee_id=employee_id,
        computer_name=client_info.computer_name,
        windows_user=client_info.windows_user,
        mac_address=client_info.mac_address,
        ip_address=client_info.ip_address,
        os_version=client_info.os_version,
        cpu_id=client_info.cpu_id,
        disk_serial=client_info.disk_serial,
        client_version=client_info.client_version,
        last_seen=beijing_now,
        hardware_fingerprint=client_info.hardware_fingerprint,
        hardware_parts=client_info.hardware_parts,
        has_hardware=client_info.has_hardware or False,
        config={
            "interval": client_info.interval or Config.SCREENSHOT_INTERVAL,
            "quality": client_info.quality or Config.SCREENSHOT_QUALITY,
            "format": client_info.format or Config.SCREENSHOT_FORMAT,
            "enable_heartbeat": True,
            "enable_batch_upload": True,
        },
        capabilities=client_info.capabilities or [],
    )

    db.add(new_client)
    db.commit()
    db.refresh(new_client)

    logger.info(f"✨ 新设备注册成功: {client_id} -> {employee_id}")
    return new_client


@app.post("/api/client/{client_id}/heartbeat", tags=["客户端"])
async def client_heartbeat(
    client_id: str,
    heartbeat: schemas.Heartbeat,  # Pydantic模型会自动处理类型转换
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """客户端心跳 - 修复版：利用增强的Heartbeat模型自动处理类型"""

    beijing_now = get_beijing_now()

    logger.debug(f"收到心跳: client={client_id}, paused={heartbeat.paused}")

    client = (
        db.query(models.Client).filter(models.Client.client_id == client_id).first()
    )

    if not client:
        raise HTTPException(status_code=404, detail="客户端不存在")

    # 更新客户端信息
    client.last_seen = beijing_now
    client.last_stats = heartbeat.stats
    if heartbeat.ip_address:
        client.ip_address = heartbeat.ip_address

    db.commit()

    # 随机记录活动
    import random

    if random.randint(1, 10) == 1:
        background_tasks.add_task(
            log_activity,
            client.employee_id,
            "heartbeat",
            {"client_id": client_id, "status": heartbeat.status},
        )

    return {
        "status": "ok",
        "server_time": beijing_now.isoformat(),
        "config": client.config,
    }


@app.get("/api/client/{client_id}/config", tags=["客户端"])
async def get_client_config(client_id: str, db: Session = Depends(get_db)):
    """获取客户端配置"""
    client = (
        db.query(models.Client).filter(models.Client.client_id == client_id).first()
    )

    if client:
        return client.config

    # 返回默认配置
    return {
        "interval": Config.SCREENSHOT_INTERVAL,
        "quality": Config.SCREENSHOT_QUALITY,
        "format": Config.SCREENSHOT_FORMAT,
        "enable_heartbeat": True,
        "enable_batch_upload": True,
    }


# ==================== 截图上传接口 ====================
@app.post("/api/upload", tags=["截图"])
async def upload_screenshot(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    employee_id: str = Form(...),
    client_id: Optional[str] = Form(None),
    computer_name: Optional[str] = Form(None),
    windows_user: Optional[str] = Form(None),
    timestamp: Optional[str] = Form(None),
    encrypted: str = Form("false"),
    format: str = Form("webp"),
    file: UploadFile = File(...),
):
    """
    上传截图 - 修复时区问题
    数据库是 timestamptz，直接存储带时区的时间
    """

    # ========== 导入所需模块 ==========
    from PIL import Image  # ✅ 添加这个导入

    # ========== 1. 类型转换 ==========
    is_encrypted = encrypted.lower() in ("true", "1", "yes", "on")

    logger.info(
        f"📸 收到上传请求: "
        f"employee={employee_id}, "
        f"client={client_id}, "
        f"encrypted={encrypted} -> {is_encrypted}, "
        f"format={format}"
    )

    # ========== 2. 验证文件类型 ==========
    allowed_extensions = {"jpg", "jpeg", "png", "webp", "bmp"}
    file_ext = file.filename.split(".")[-1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_ext}")

    # ========== 3. 时间处理 ==========
    # 获取当前北京时间（带时区）
    beijing_now = get_beijing_now()

    # 解析截图时间（客户端传来的时间是北京时间）
    try:
        if timestamp:
            # 尝试解析多种格式
            try:
                screenshot_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    screenshot_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
                except ValueError:
                    screenshot_time = datetime.strptime(timestamp, "%Y-%m-%d")

            # 添加北京时间时区
            screenshot_time = screenshot_time.replace(tzinfo=BEIJING_TZ)
        else:
            screenshot_time = beijing_now
    except Exception as e:
        logger.warning(f"时间解析失败: {e}, 使用当前北京时间")
        screenshot_time = beijing_now

    logger.info(f"截图时间(北京时间): {format_beijing_time(screenshot_time)}")
    logger.info(f"当前时间(北京时间): {format_beijing_time(beijing_now)}")

    # ========== 4. 处理客户端 ==========
    client = None
    if client_id:
        client = (
            db.query(models.Client).filter(models.Client.client_id == client_id).first()
        )

    if client:
        # 🚨 关键：直接存储带时区的时间
        client.last_seen = beijing_now
        logger.debug(f"客户端 {client_id} 最后在线时间已更新")

        if not client.employee_id:
            client.employee_id = employee_id
            logger.info(f"客户端 {client_id} 已关联员工 {employee_id}")
    elif client_id:
        # 客户端不存在但提供了client_id，创建新客户端
        logger.info(f"客户端 {client_id} 不存在，创建新记录")
        client = models.Client(
            client_id=client_id,
            employee_id=employee_id,
            computer_name=computer_name,
            windows_user=windows_user,
            last_seen=beijing_now,  # ✅ 直接存带时区的时间
            config={
                "interval": Config.SCREENSHOT_INTERVAL,
                "quality": Config.SCREENSHOT_QUALITY,
                "format": Config.SCREENSHOT_FORMAT,
                "enable_heartbeat": True,
                "enable_batch_upload": True,
            },
        )
        db.add(client)

    # ========== 5. 查找或创建员工 ==========
    employee = (
        db.query(models.Employee)
        .filter(models.Employee.employee_id == employee_id)
        .first()
    )

    if not employee:
        # 生成员工姓名
        if computer_name and windows_user:
            employee_name = f"{computer_name} - {windows_user}"
        elif computer_name:
            employee_name = computer_name
        elif windows_user:
            employee_name = windows_user
        else:
            employee_name = (
                f"员工_{employee_id[-8:] if len(employee_id) > 8 else employee_id}"
            )

        employee = models.Employee(
            employee_id=employee_id,
            name=employee_name,
            computer_name=computer_name,
            windows_user=windows_user,
            department="自动注册",
            position="员工",
            status="active",
            created_at=beijing_now,  # ✅ 直接存带时区的时间
        )
        db.add(employee)
        logger.info(f"✅ 自动创建员工: {employee_id} - {employee_name}")

    # ========== 6. 保存文件 ==========
    # 生成安全的文件路径
    safe_employee_id = employee_id.replace("\\", "/").replace(":", "_")
    date_str = screenshot_time.strftime("%Y-%m-%d")
    time_str = screenshot_time.strftime("%H-%M-%S")

    # 文件名格式: employee_id/YYYY-MM-DD/HH-MM-SS.format
    filename = f"{safe_employee_id}/{date_str}/{time_str}.{format}"
    file_path = STORAGE_PATH / filename

    # 确保目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存文件
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.debug(f"文件已保存: {file_path}")
    except Exception as e:
        logger.error(f"保存文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")

    # 获取文件大小
    file_size = file_path.stat().st_size

    # ========== 7. 创建缩略图（异步）==========
    thumbnail_filename = f"{safe_employee_id}/{date_str}/{time_str}_thumb.webp"
    thumbnail_path = STORAGE_PATH / thumbnail_filename
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

    # 添加缩略图生成任务
    background_tasks.add_task(create_thumbnail, str(file_path), str(thumbnail_path))

    # ========== 8. 获取图片尺寸 ==========
    width = height = 0
    try:
        with Image.open(file_path) as img:  # ✅ 现在可以使用 Image 了
            width, height = img.size
        logger.debug(f"图片尺寸: {width}x{height}")
    except Exception as e:
        logger.warning(f"获取图片尺寸失败: {e}")

    # ========== 9. 保存截图记录 ==========
    screenshot = models.Screenshot(
        employee_id=employee_id,
        client_id=client_id,
        filename=str(filename),
        thumbnail=str(thumbnail_filename),
        file_size=file_size,
        width=width,
        height=height,
        storage_url=f"/screenshots/{filename}",
        # 🚨 关键：直接存储带时区的时间
        screenshot_time=screenshot_time,  # ✅ 北京时间带时区
        uploaded_at=beijing_now,  # ✅ 北京时间带时区
        computer_name=computer_name,
        windows_user=windows_user,
        image_format=format,
        is_encrypted=is_encrypted,
    )

    db.add(screenshot)

    # 先 flush 以获取 screenshot.id
    db.flush()

    # ========== 10. 记录活动日志 ==========
    try:
        activity = models.Activity(
            employee_id=employee_id,
            action="screenshot",
            details={
                "screenshot_id": screenshot.id,
                "file_size": file_size,
                "format": format,
                "filename": filename,
            },
            created_at=beijing_now,  # ✅ 直接存带时区的时间
        )
        db.add(activity)
    except Exception as e:
        logger.error(f"记录活动失败: {e}")

    # ========== 11. 提交事务 ==========
    try:
        db.commit()
        logger.info(
            f"✅ 截图保存成功: {filename} "
            f"({file_size/1024:.1f}KB) - 员工: {employee_id}"
        )
        logger.info(f"  截图时间: {format_beijing_time(screenshot_time)}")
    except Exception as e:
        db.rollback()
        logger.error(f"数据库提交失败: {e}")
        # 如果数据库提交失败，删除已保存的文件
        try:
            if file_path.exists():
                file_path.unlink()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"数据库保存失败: {str(e)}")

    # ========== 12. 返回结果 ==========
    return {
        "success": True,
        "id": screenshot.id,
        "url": screenshot.storage_url,
        "thumbnail": f"/screenshots/{thumbnail_filename}",
        "size": file_size,
        "size_str": format_file_size_util(file_size),
        "employee_id": employee_id,
        "employee_name": employee.name if employee else employee_id,
        "client_id": client_id,
        "timestamp": format_beijing_time(screenshot_time),
        "width": width,
        "height": height,
        "format": format,
        "encrypted": is_encrypted,
    }


# ========== 辅助函数 ==========


def create_thumbnail(image_path: str, thumbnail_path: str):
    """
    创建缩略图（后台任务）

    Args:
        image_path: 原图路径
        thumbnail_path: 缩略图保存路径
    """
    try:
        from PIL import Image

        # 确保缩略图目录存在
        Path(thumbnail_path).parent.mkdir(parents=True, exist_ok=True)

        # 打开原图并创建缩略图
        with Image.open(image_path) as img:
            # 保持宽高比，限制最大尺寸
            img.thumbnail((320, 240), Image.Resampling.LANCZOS)

            # 保存为 WebP 格式
            img.save(
                thumbnail_path, "WEBP", quality=Config.THUMBNAIL_QUALITY, optimize=True
            )

        logger.debug(f"✅ 缩略图创建成功: {thumbnail_path}")

    except Exception as e:
        logger.error(f"❌ 创建缩略图失败: {e}")


@app.post("/api/upload/batch", tags=["截图"])
async def upload_batch(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    client_id: str = Form(...),
    employee_id: str = Form(...),
    count: int = Form(...),
    batch: UploadFile = File(...),
):
    """批量上传截图"""

    # ===== 修改点：使用北京时间生成文件名 =====
    # 保存ZIP文件
    zip_path = (
        STORAGE_PATH
        / "temp"
        / f"batch_{get_beijing_now().strftime('%Y%m%d_%H%M%S')}.zip"
        # 原来是：datetime.now().strftime('%Y%m%d_%H%M%S')
    )
    # ======================================

    zip_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(batch.file, buffer)

        # 异步处理ZIP文件
        background_tasks.add_task(
            process_batch_upload, str(zip_path), client_id, employee_id, count
        )

        return {"success": True, "message": f"批量上传已接收，共 {count} 个文件"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {e}")


# ==================== 员工管理接口 ====================
@app.get("/api/employees", tags=["员工"])
def get_employees(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    online_only: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取员工列表 - 修复时区问题
    数据库是 timestamptz，直接用北京时间判断在线状态
    """
    logger = logging.getLogger(__name__)

    # ===== 1. 获取北京时间 =====
    beijing_now = get_beijing_now()
    cutoff_time = beijing_now - timedelta(minutes=10)  # 10分钟前的北京时间

    logger.debug(f"员工列表请求参数:")
    logger.debug(f"  skip={skip}, limit={limit}, status={status}")
    logger.debug(f"  online_only={online_only}, search={search}")
    logger.debug(f"  当前北京时间: {beijing_now}")
    logger.debug(f"  在线判断阈值: {cutoff_time}")

    # ===== 2. 基础查询 =====
    query = db.query(models.Employee)

    # 状态筛选
    if status:
        query = query.filter(models.Employee.status == status)

    # 搜索
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.Employee.name.ilike(search_term),
                models.Employee.employee_id.ilike(search_term),
                models.Employee.department.ilike(search_term),
                models.Employee.position.ilike(search_term),
            )
        )

    # ===== 3. 在线筛选 =====
    if online_only is not None:
        from sqlalchemy import exists, and_

        # 🚨 关键：直接用北京时间比较，因为 last_seen 是 timestamptz
        online_subquery = exists().where(
            and_(
                models.Client.employee_id == models.Employee.employee_id,
                models.Client.last_seen >= cutoff_time,  # ✅ 直接用北京时间
            )
        )

        if online_only:
            query = query.filter(online_subquery)
            logger.debug(f"应用在线筛选，阈值: {cutoff_time}")
        else:
            query = query.filter(~online_subquery)
            logger.debug(f"应用离线筛选，阈值: {cutoff_time}")

    # ===== 4. 总数统计 =====
    total = query.count()

    # ===== 5. 分页查询 =====
    employees = (
        query.options(selectinload(models.Employee.clients))
        .offset(skip)
        .limit(limit)
        .all()
    )

    # ===== 6. 格式化返回数据 =====
    items = []
    for emp in employees:
        emp_dict = emp.to_dict()
        # 在线状态已经在 to_dict() 中通过 has_active_clients 计算好了
        items.append(emp_dict)

    logger.debug(f"返回 {len(items)} 条记录，总数: {total}")

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ===== 修改点1：日期路由必须放在最前面，使用 path 参数 =====
@app.get("/api/employees/{employee_id:path}/dates", tags=["员工"])
def get_employee_dates(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取员工有截图的所有日期 - 统一格式"""
    screenshots = (
        db.query(models.Screenshot)
        .filter(models.Screenshot.employee_id == employee_id)
        .all()
    )

    dates = {}
    for s in screenshots:
        date = s.screenshot_time.strftime("%Y-%m-%d")
        dates[date] = dates.get(date, 0) + 1

    result = [
        {"date": d, "count": dates[d]} for d in sorted(dates.keys(), reverse=True)
    ]

    # ✅ 统一返回格式
    return {"items": result, "total": len(result)}


# ===== 修改点2：获取单个员工，使用 path 参数 =====
@app.get(
    "/api/employees/{employee_id:path}", response_model=schemas.Employee, tags=["员工"]
)
def get_employee(
    employee_id: str,  # 这里会捕获完整的 "OS-20250218QMGZ\Administrator"
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取单个员工"""
    employee = (
        db.query(models.Employee)
        .filter(models.Employee.employee_id == employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")

    return employee


# ==============================================


@app.post("/api/employees", response_model=schemas.Employee, tags=["员工"])
def create_employee(
    employee: schemas.EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """创建员工"""
    db_employee = (
        db.query(models.Employee)
        .filter(models.Employee.employee_id == employee.employee_id)
        .first()
    )

    if db_employee:
        raise HTTPException(status_code=400, detail="员工ID已存在")

    db_employee = models.Employee(**employee.dict())
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)

    logger.info(f"员工创建: {employee.employee_id}")
    return db_employee


# ===== 修改点3：更新员工（你已经改好了） =====
@app.put(
    "/api/employees/{employee_id:path}", response_model=schemas.Employee, tags=["员工"]
)
def update_employee(
    employee_id: str,  # 这里会捕获完整的 "OS-20250218QMGZ\Administrator"
    employee_update: schemas.EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """更新员工信息"""
    db_employee = (
        db.query(models.Employee)
        .filter(models.Employee.employee_id == employee_id)  # 直接用完整ID查询
        .first()
    )

    if not db_employee:
        raise HTTPException(status_code=404, detail="员工不存在")

    for key, value in employee_update.dict(exclude_unset=True).items():
        setattr(db_employee, key, value)

    db.commit()
    db.refresh(db_employee)

    logger.info(f"员工更新: {employee_id}")
    return db_employee


# ==========================================


# ===== 修改点4：删除员工，使用 path 参数 =====
@app.delete("/api/employees/{employee_id:path}", tags=["员工"])
def delete_employee(
    employee_id: str,  # 这里会捕获完整的 "OS-20250218QMGZ\Administrator"
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """删除员工"""
    db_employee = (
        db.query(models.Employee)
        .filter(models.Employee.employee_id == employee_id)
        .first()
    )

    if not db_employee:
        raise HTTPException(status_code=404, detail="员工不存在")

    # 检查是否有截图
    screenshot_count = (
        db.query(models.Screenshot)
        .filter(models.Screenshot.employee_id == employee_id)
        .count()
    )

    if screenshot_count > 0:
        # 软删除或提示
        db_employee.status = "deleted"
        db.commit()
        return {"message": f"员工已标记为删除，关联 {screenshot_count} 张截图"}

    db.delete(db_employee)
    db.commit()

    logger.info(f"员工删除: {employee_id}")
    return {"message": "员工已删除"}


# ==================== 截图接口 ====================
@app.get("/api/screenshots", tags=["截图"])
def get_screenshots(
    employee_id: Optional[str] = None,
    client_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取截图列表 - 统一北京时间处理
    所有时间参数都视为北京时间，数据库存储也是北京时间
    支持游标分页优化大数据量查询
    """
    from sqlalchemy import text
    import re

    logger = logging.getLogger(__name__)

    try:
        # ==============================
        # 1. 参数验证（保持不变）
        # ==============================
        if skip < 0 or limit < 1 or limit > 1000:
            raise HTTPException(status_code=400, detail="无效的分页参数")

        # 日期格式验证（支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS）
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        datetime_pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$"
        time_pattern = r"^\d{2}:\d{2}(:\d{2})?$"

        # 验证开始日期
        if start_date:
            if not (
                re.match(date_pattern, start_date)
                or re.match(datetime_pattern, start_date)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="开始日期格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
                )

        # 验证结束日期
        if end_date:
            if not (
                re.match(date_pattern, end_date) or re.match(datetime_pattern, end_date)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="结束日期格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
                )

        # 验证时间参数
        if start_time and not re.match(time_pattern, start_time):
            raise HTTPException(
                status_code=400, detail="开始时间格式应为 HH:MM 或 HH:MM:SS"
            )
        if end_time and not re.match(time_pattern, end_time):
            raise HTTPException(
                status_code=400, detail="结束时间格式应为 HH:MM 或 HH:MM:SS"
            )

        # ==============================
        # 2. 构建基础查询（保持不变）
        # ==============================
        base_sql = """
            FROM screenshots s
            LEFT JOIN employees e ON s.employee_id = e.employee_id
            WHERE 1=1
        """

        select_sql = """
            SELECT
                s.id,
                s.employee_id,
                s.client_id,
                s.filename,
                s.thumbnail,
                s.file_size,
                s.width,
                s.height,
                s.storage_url,
                s.uploaded_at,
                s.screenshot_time,
                s.computer_name,
                s.windows_user,
                s.image_format,
                s.is_encrypted,
                e.name as employee_name
        """

        params = {}

        # 员工筛选
        if employee_id:
            base_sql += " AND s.employee_id = :employee_id"
            params["employee_id"] = employee_id

        # 客户端筛选
        if client_id:
            base_sql += " AND s.client_id = :client_id"
            params["client_id"] = client_id

        # ==============================
        # 3. 构建完整的时间字符串（北京时间）
        # ==============================
        full_start_datetime = None
        full_end_datetime = None

        # 处理开始时间 - 构建北京时间字符串
        if start_date and " " in start_date:
            full_start_datetime = start_date
            logger.debug(f"开始时间(北京时间): {start_date}")
        elif start_date and start_time:
            full_start_datetime = f"{start_date} {start_time}"
            if len(start_time) == 5:
                full_start_datetime += ":00"
            logger.debug(f"开始时间(北京时间): {full_start_datetime}")
        elif start_date:
            full_start_datetime = f"{start_date} 00:00:00"
            logger.debug(f"开始时间(北京时间): {full_start_datetime}")
        elif start_time:
            today = get_beijing_now().strftime("%Y-%m-%d")
            full_start_datetime = f"{today} {start_time}"
            if len(start_time) == 5:
                full_start_datetime += ":00"
            logger.debug(f"开始时间(北京时间): {full_start_datetime}")

        # 处理结束时间 - 构建北京时间字符串
        if end_date and " " in end_date:
            full_end_datetime = end_date
            logger.debug(f"结束时间(北京时间): {end_date}")
        elif end_date and end_time:
            full_end_datetime = f"{end_date} {end_time}"
            if len(end_time) == 5:
                full_end_datetime += ":59"
            logger.debug(f"结束时间(北京时间): {full_end_datetime}")
        elif end_date:
            full_end_datetime = f"{end_date} 23:59:59"
            logger.debug(f"结束时间(北京时间): {full_end_datetime}")
        elif end_time:
            today = get_beijing_now().strftime("%Y-%m-%d")
            full_end_datetime = f"{today} {end_time}"
            if len(end_time) == 5:
                full_end_datetime += ":59"
            logger.debug(f"结束时间(北京时间): {full_end_datetime}")

        # ==============================
        # 3-1. 🚨 将北京时间转换为 UTC 用于数据库查询
        # ==============================
        from server_timezone import parse_beijing_datetime, to_utc_time, make_naive

        # 转换开始时间
        if full_start_datetime:
            try:
                # 解析北京时间
                beijing_dt = parse_beijing_datetime(full_start_datetime)
                if beijing_dt:
                    # 转换为 UTC 并转为 naive
                    utc_dt = to_utc_time(beijing_dt)
                    utc_naive = make_naive(utc_dt)

                    base_sql += " AND s.screenshot_time >= :start_datetime"
                    params["start_datetime"] = utc_naive
                    logger.debug(f"开始时间(UTC): {utc_naive}")
            except Exception as e:
                logger.error(f"开始时间转换失败: {e}")

        # 转换结束时间
        if full_end_datetime:
            try:
                # 解析北京时间
                beijing_dt = parse_beijing_datetime(full_end_datetime)
                if beijing_dt:
                    # 转换为 UTC 并转为 naive
                    utc_dt = to_utc_time(beijing_dt)
                    utc_naive = make_naive(utc_dt)

                    base_sql += " AND s.screenshot_time <= :end_datetime"
                    params["end_datetime"] = utc_naive
                    logger.debug(f"结束时间(UTC): {utc_naive}")
            except Exception as e:
                logger.error(f"结束时间转换失败: {e}")

        # 验证时间范围（使用 UTC 时间比较）
        if params.get("start_datetime") and params.get("end_datetime"):
            if params["start_datetime"] > params["end_datetime"]:
                raise HTTPException(status_code=400, detail="开始时间不能大于结束时间")
            logger.info(
                f"时间范围(UTC): {params['start_datetime']} 至 {params['end_datetime']}"
            )

        # ==============================
        # 4. 获取总数
        # ==============================
        count_sql = f"SELECT COUNT(*) {base_sql}"
        total = db.execute(text(count_sql), params).scalar() or 0

        # ==============================
        # 5. 游标分页优化
        # ==============================
        CURSOR_THRESHOLD = 1000

        if skip >= CURSOR_THRESHOLD:
            logger.debug(f"使用游标分页: skip={skip}, threshold={CURSOR_THRESHOLD}")

            cursor_sql = f"""
                SELECT screenshot_time 
                {base_sql} 
                ORDER BY screenshot_time DESC 
                OFFSET :skip LIMIT 1
            """
            cursor_params = params.copy()
            cursor_params["skip"] = skip

            cursor_result = db.execute(text(cursor_sql), cursor_params).first()

            if cursor_result and cursor_result[0]:
                cursor_time = cursor_result[0]
                base_sql_with_cursor = (
                    base_sql + " AND s.screenshot_time <= :cursor_time"
                )
                cursor_params_with_time = params.copy()
                cursor_params_with_time["cursor_time"] = cursor_time

                sql = f"{select_sql} {base_sql_with_cursor} ORDER BY s.screenshot_time DESC LIMIT :limit"
                query_params = cursor_params_with_time
                query_params["limit"] = limit

                logger.debug(f"游标时间: {cursor_time}")
            else:
                logger.warning(f"游标查询失败，回退到普通分页: skip={skip}")
                sql = f"{select_sql} {base_sql} ORDER BY s.screenshot_time DESC OFFSET :skip LIMIT :limit"
                query_params = params.copy()
                query_params["skip"] = skip
                query_params["limit"] = limit
        else:
            logger.debug(f"使用普通分页: skip={skip}")
            sql = f"{select_sql} {base_sql} ORDER BY s.screenshot_time DESC OFFSET :skip LIMIT :limit"
            query_params = params.copy()
            query_params["skip"] = skip
            query_params["limit"] = limit

        # ==============================
        # 6. 执行查询
        # ==============================
        result = db.execute(text(sql), query_params).fetchall()

        # ✅ 使用统一格式化函数
        screenshots = [format_screenshot_response(dict(row._mapping)) for row in result]

        logger.info(
            f"截图查询成功: 总数={total}, 返回={len(screenshots)}条, "
            f"分页: skip={skip}, limit={limit}, 使用游标={skip >= CURSOR_THRESHOLD}"
        )

        return {
            "items": screenshots,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": (skip + len(screenshots)) < total,
            "timezone": "Asia/Shanghai",
            "cursor_used": skip >= CURSOR_THRESHOLD,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"截图接口错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@app.get("/api/screenshots/{employee_id}/{date}", tags=["截图"])
def get_screenshots_by_date(
    employee_id: str,
    date: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取员工指定日期的截图 - 统一格式
    保留所有原有字段，同时添加分页信息
    """
    from sqlalchemy import text
    import logging

    logger = logging.getLogger(__name__)

    try:
        # ========== 1. 解析日期 ==========
        try:
            start = datetime.strptime(date, "%Y-%m-%d")
            end = start + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        # ========== 2. 获取总数 ==========
        count_sql = """
            SELECT COUNT(*) 
            FROM screenshots s
            WHERE s.employee_id = :employee_id
                AND s.screenshot_time >= :start_date
                AND s.screenshot_time < :end_date
        """

        count_params = {
            "employee_id": employee_id,
            "start_date": start,
            "end_date": end,
        }

        total = db.execute(text(count_sql), count_params).scalar() or 0

        # ========== 3. 获取截图数据 ==========
        sql = """
            SELECT 
                s.id,
                s.employee_id,
                s.client_id,
                s.filename,
                s.thumbnail,
                s.file_size,
                s.width,
                s.height,
                s.storage_url,
                s.uploaded_at,
                s.screenshot_time,
                s.computer_name,
                s.windows_user,
                s.image_format,
                s.is_encrypted,
                e.name as employee_name
            FROM screenshots s
            LEFT JOIN employees e ON s.employee_id = e.employee_id
            WHERE s.employee_id = :employee_id
                AND s.screenshot_time >= :start_date
                AND s.screenshot_time < :end_date
            ORDER BY s.screenshot_time DESC
        """

        params = {"employee_id": employee_id, "start_date": start, "end_date": end}

        # 执行查询
        result = db.execute(text(sql), params).fetchall()

        # ✅ 使用统一格式化函数
        screenshots = [format_screenshot_response(dict(row._mapping)) for row in result]

        # ========== 5. ✅ 统一返回格式 ==========
        return {
            "items": screenshots,
            "total": total,
            "employee_id": employee_id,
            "date": date,
            "returned": len(screenshots),
            "has_more": False,
            "timezone": "Asia/Shanghai",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取员工日期截图失败: {str(e)}", exc_info=True)
        return {
            "items": [],
            "total": 0,
            "employee_id": employee_id,
            "date": date,
            "returned": 0,
            "has_more": False,
            "timezone": "Asia/Shanghai",
            "error": str(e) if hasattr(Config, "DEBUG") and Config.DEBUG else None,
        }


@app.get("/api/screenshots/recent", tags=["截图"])
def get_recent_screenshots(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取最近的截图 - 统一格式
    保留所有原有字段，同时添加分页信息
    """
    from sqlalchemy import text
    import logging

    logger = logging.getLogger(__name__)

    try:
        # ========== 1. 获取总数 ==========
        count_sql = """
            SELECT COUNT(*) 
            FROM screenshots s
        """
        total = db.execute(text(count_sql)).scalar() or 0

        # ========== 2. 获取最近截图数据 ==========
        sql = """
            SELECT 
                s.id,
                s.employee_id,
                s.client_id,
                s.filename,
                s.thumbnail,
                s.file_size,
                s.width,
                s.height,
                s.storage_url,
                s.uploaded_at,
                s.screenshot_time,
                s.computer_name,
                s.windows_user,
                s.image_format,
                s.is_encrypted,
                e.name as employee_name
            FROM screenshots s
            LEFT JOIN employees e ON s.employee_id = e.employee_id
            ORDER BY s.screenshot_time DESC
            LIMIT :limit
        """

        params = {"limit": limit}

        # 执行查询
        result = db.execute(text(sql), params).fetchall()

        # ✅ 使用统一格式化函数
        screenshots = [format_screenshot_response(dict(row._mapping)) for row in result]

        # ========== 4. ✅ 统一返回格式 ==========
        return {
            "items": screenshots,
            "total": total,
            "limit": limit,
            "returned": len(screenshots),
            "has_more": len(screenshots) == limit,
            "timezone": "Asia/Shanghai",
        }

    except Exception as e:
        logger.error(f"获取最近截图失败: {str(e)}", exc_info=True)
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "returned": 0,
            "has_more": False,
            "timezone": "Asia/Shanghai",
            "error": str(e) if Config.DEBUG else None,
        }


# ==================== 客户端管理接口 ====================
@app.get("/api/clients", tags=["客户端"])
def get_clients(
    skip: int = 0,
    limit: int = 100,
    online_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取客户端列表 - 修复时区问题
    数据库是 timestamptz，直接用北京时间判断在线状态
    """
    logger = logging.getLogger(__name__)

    # ===== 1. 获取北京时间 =====
    beijing_now = get_beijing_now()
    cutoff_time = beijing_now - timedelta(minutes=10)  # 10分钟前的北京时间

    logger.debug(
        f"客户端列表请求: skip={skip}, limit={limit}, online_only={online_only}"
    )
    logger.debug(f"当前北京时间: {beijing_now}")
    logger.debug(f"在线判断阈值: {cutoff_time}")

    # ===== 2. 构建查询 =====
    query = db.query(models.Client)

    # ===== 3. 在线筛选 =====
    if online_only:
        query = query.filter(
            models.Client.last_seen >= cutoff_time
        )  # ✅ 直接用北京时间

    # ===== 4. 获取总数 =====
    total = query.count()

    # ===== 5. 获取分页数据 =====
    clients = (
        query.order_by(models.Client.last_seen.desc()).offset(skip).limit(limit).all()
    )

    # ===== 6. 格式化返回数据 =====
    items = [c.to_dict() for c in clients]  # to_dict() 已经处理好时间

    logger.debug(f"返回 {len(items)} 条记录，总数: {total}")

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(clients)) < total,
    }


@app.get("/api/clients/online", tags=["客户端"])
def get_online_clients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取在线客户端"""
    cutoff = get_utc_now() - timedelta(minutes=10)
    clients = db.query(models.Client).filter(models.Client.last_seen >= cutoff).all()

    return [
        {
            "client_id": c.client_id,
            "employee_id": c.employee_id,
            "computer_name": c.computer_name,
            "ip_address": c.ip_address,
            "last_seen": c.last_seen.isoformat(),
            "client_version": c.client_version,
        }
        for c in clients
    ]


@app.delete("/api/clients/{client_id}", tags=["客户端"])
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """删除客户端"""
    client = (
        db.query(models.Client).filter(models.Client.client_id == client_id).first()
    )

    if not client:
        raise HTTPException(status_code=404, detail="客户端不存在")

    db.delete(client)
    db.commit()

    logger.info(f"客户端删除: {client_id}")
    return {"message": "客户端已删除"}


# ==================== 统计接口 ====================
@app.get("/api/stats", tags=["统计"])
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取系统统计信息 - 数据库存储的是北京时间"""

    from server_timezone import get_beijing_now, get_date_range_for_day
    from sqlalchemy import func
    import logging

    logger = logging.getLogger(__name__)

    # ===== 1. 获取北京时间作为基准 =====
    beijing_now = get_beijing_now()
    logger.debug(f"统计计算 - 北京时间: {beijing_now}")

    # ===== 2. 获取今日范围（直接使用北京时间）=====
    today_start, today_end = get_date_range_for_day(beijing_now)

    # ===== 3. 昨日范围 =====
    yesterday = beijing_now - timedelta(days=1)
    yesterday_start, yesterday_end = get_date_range_for_day(yesterday)

    # ===== 4. 本周开始（7天前）=====
    week_ago = beijing_now - timedelta(days=7)

    # ===== 5. 在线客户端阈值 =====
    cutoff = beijing_now - timedelta(minutes=10)

    # ===== 6. 今日截图（直接使用北京时间查询）=====
    today_count = (
        db.query(models.Screenshot)
        .filter(
            models.Screenshot.screenshot_time >= today_start,
            models.Screenshot.screenshot_time < today_end,
        )
        .count()
    )

    # ===== 7. 昨日截图 =====
    yesterday_count = (
        db.query(models.Screenshot)
        .filter(
            models.Screenshot.screenshot_time >= yesterday_start,
            models.Screenshot.screenshot_time < yesterday_end,
        )
        .count()
    )

    # ===== 8. 本周截图 =====
    week_count = (
        db.query(models.Screenshot)
        .filter(models.Screenshot.screenshot_time >= week_ago)
        .count()
    )

    # ===== 9. 在线客户端 =====
    online_clients = (
        db.query(models.Client).filter(models.Client.last_seen >= cutoff).count()
    )

    # ===== 10. 总数 =====
    total_screenshots = db.query(models.Screenshot).count()
    total_employees = db.query(models.Employee).count()
    total_clients = db.query(models.Client).count()

    # ===== 11. 存储大小 =====
    total_size = db.query(func.sum(models.Screenshot.file_size)).scalar() or 0

    # ===== 12. 各格式统计 =====
    webp_count = (
        db.query(models.Screenshot)
        .filter(models.Screenshot.image_format == "webp")
        .count()
    )
    jpg_count = (
        db.query(models.Screenshot)
        .filter(models.Screenshot.image_format == "jpg")
        .count()
    )

    # ===== 13. 每小时活动（直接使用北京时间）=====
    hourly = []
    for i in range(24):
        start = beijing_now.replace(hour=i, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        count = (
            db.query(models.Screenshot)
            .filter(
                models.Screenshot.screenshot_time >= start,
                models.Screenshot.screenshot_time < end,
            )
            .count()
        )
        hourly.append(count)

    # ===== 14. 最近活动（直接使用数据库中的时间，已经是北京时间）=====
    recent_activities = (
        db.query(models.Activity)
        .order_by(models.Activity.created_at.desc())
        .limit(10)
        .all()
    )

    formatted_activities = []
    for a in recent_activities:
        # 获取员工姓名
        employee_name = a.employee_id  # 默认显示ID
        if a.employee_id:
            employee = (
                db.query(models.Employee)
                .filter(models.Employee.employee_id == a.employee_id)
                .first()
            )
            if employee and employee.name:
                employee_name = employee.name  # ✅ 使用员工姓名

        time_str = a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None
        formatted_activities.append(
            {
                "employee_id": a.employee_id,  # 保留ID供参考
                "employee_name": employee_name,  # ✅ 新增姓名字段
                "action": a.action,
                "time": time_str,
            }
        )

    # ===== 15. 各员工截图统计 =====
    # 创建一个列表来存储所有有截图的员工数据
    all_employee_stats = []

    # 获取所有员工
    all_employees = db.query(models.Employee).all()

    for emp in all_employees:
        # 今日截图
        today_emp = (
            db.query(models.Screenshot)
            .filter(
                models.Screenshot.employee_id == emp.employee_id,
                models.Screenshot.screenshot_time >= today_start,
                models.Screenshot.screenshot_time < today_end,
            )
            .count()
        )

        # 累计截图
        total_emp = (
            db.query(models.Screenshot)
            .filter(models.Screenshot.employee_id == emp.employee_id)
            .count()
        )

        # 只添加有截图的员工（今日截图>0 或 累计截图>0）
        if today_emp > 0 or total_emp > 0:
            all_employee_stats.append(
                {
                    "id": emp.employee_id,
                    "name": emp.name,
                    "today": today_emp,
                    "total": total_emp,
                }
            )

    # 按今日截图数量降序排序
    all_employee_stats.sort(key=lambda x: x["today"], reverse=True)

    # 取前5名
    top_employees = all_employee_stats[:5]

    # 如果不足5个，就返回全部
    # top_employees = all_employee_stats  # 如果想返回全部，可以用这行

    logger.info(f"统计结果:")
    logger.info(f"  今日截图: {today_count}")
    logger.info(
        f"  最近活动示例: {formatted_activities[0] if formatted_activities else None}"
    )

    return {
        "today": today_count,
        "yesterday": yesterday_count,
        "week": week_count,
        "total": total_screenshots,
        "employees": total_employees,
        "clients": total_clients,
        "online": online_clients,
        "storage_mb": round(total_size / (1024 * 1024), 2),
        "image_formats": {
            "webp": webp_count,
            "jpg": jpg_count,
            "other": total_screenshots - webp_count - jpg_count,
        },
        "hourly": hourly,
        "recent_activities": formatted_activities,
        "top_employees": top_employees,
        "auto_cleanup": {
            "enabled": Config.AUTO_CLEANUP_ENABLED,
            "interval_hours": Config.CLEANUP_INTERVAL / 3600,
            "retention_hours": Config.SCREENSHOT_RETENTION_HOURS,
        },
    }


@app.get("/api/activities", tags=["统计"])
def get_activities(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取活动日志 - 统一格式"""
    activities = (
        db.query(models.Activity)
        .order_by(models.Activity.created_at.desc())
        .limit(limit)
        .all()
    )

    items = [
        {
            "employee_id": a.employee_id,
            "action": a.action,
            "time": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for a in activities
    ]

    return {"items": items, "total": len(items), "limit": limit, "returned": len(items)}


# ==================== 清理接口 ====================


@app.post("/api/cleanup", tags=["系统"])
def manual_cleanup(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_active_user),
):
    """手动清理旧截图"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    background_tasks.add_task(cleanup.cleanup_old_data_once)

    return {
        "message": "清理任务已启动",
        "retention_hours": Config.SCREENSHOT_RETENTION_HOURS,
    }


@app.get("/api/cleanup/status", tags=["系统"])
def get_cleanup_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取清理状态 - 适配 timestamptz 数据库"""

    from server_timezone import get_beijing_now, to_beijing_time
    from sqlalchemy import func
    import logging

    logger = logging.getLogger(__name__)

    try:
        # ===== 1. 获取北京时间 =====
        beijing_now = get_beijing_now()
        retention_hours = Config.SCREENSHOT_RETENTION_HOURS

        # ===== 2. 计算北京时间截止时间 =====
        beijing_cutoff = beijing_now - timedelta(hours=retention_hours)

        logger.info(f"清理状态计算:")
        logger.info(f"  北京时间: {beijing_now}")
        logger.info(f"  北京时间截止: {beijing_cutoff}")

        # ===== 3. 查询待清理截图 =====
        # 🚨 关键：数据库是 timestamptz，可以直接用北京时间比较
        pending_stats = (
            db.query(
                func.count(models.Screenshot.id).label("count"),
                func.coalesce(func.sum(models.Screenshot.file_size), 0).label(
                    "total_size"
                ),
            )
            .filter(models.Screenshot.screenshot_time < beijing_cutoff)  # ✅ 直接比较
            .first()
        )

        pending_count = pending_stats.count if pending_stats else 0
        pending_size = pending_stats.total_size if pending_stats else 0

        logger.info(f"待清理截图: {pending_count}张, {pending_size/1024/1024:.2f}MB")

        # ===== 4. 获取总截图数量和大小 =====
        total_stats = db.query(
            func.count(models.Screenshot.id).label("total_count"),
            func.coalesce(func.sum(models.Screenshot.file_size), 0).label("total_size"),
        ).first()

        total_count = total_stats.total_count if total_stats else 0
        total_size = total_stats.total_size if total_stats else 0

        # ===== 5. 获取上次清理时间 =====
        last_cleanup = (
            db.query(models.Activity)
            .filter(models.Activity.action == "auto_cleanup")
            .order_by(models.Activity.created_at.desc())
            .first()
        )

        last_cleanup_time = None
        if last_cleanup and last_cleanup.created_at:
            # 🚨 数据库是 timestamptz，已经是带时区的时间
            # 直接转换为北京时间显示
            last_cleanup_time = to_beijing_time(last_cleanup.created_at)
            logger.debug(f"上次清理时间: {last_cleanup_time}")

        # ===== 6. 获取清理配置 =====
        cleanup_interval = getattr(Config, "CLEANUP_INTERVAL", 21600)  # 默认6小时
        interval_hours = cleanup_interval / 3600 if cleanup_interval else 6

        # ===== 7. 计算下次清理时间 =====
        next_cleanup_time = None
        if Config.AUTO_CLEANUP_ENABLED and last_cleanup_time:
            next_cleanup_time = last_cleanup_time + timedelta(seconds=cleanup_interval)
            logger.debug(f"下次清理时间: {next_cleanup_time}")

        # ===== 8. 获取清理时间段配置 =====
        cleanup_time = getattr(Config, "CLEANUP_TIME", None)

        # ===== 9. 计算已用存储百分比 =====
        storage_used_percent = 0
        if total_size > 0:
            storage_used_percent = round((pending_size / total_size) * 100, 2)

        # ===== 10. 返回结果（保留所有字段）=====
        return {
            # 配置信息
            "enabled": Config.AUTO_CLEANUP_ENABLED,
            "retention_hours": retention_hours,
            "interval_hours": round(interval_hours, 1),
            "cleanup_time": cleanup_time,
            # 待清理信息
            "pending_cleanup": pending_count,
            "pending_size_mb": round(pending_size / (1024 * 1024), 2),
            "pending_percent": storage_used_percent,
            # 总存储信息
            "total_screenshots": total_count,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            # 时间信息
            "current_time": beijing_now.isoformat(),
            "cutoff_time": beijing_cutoff.isoformat(),
            "last_cleanup": (
                last_cleanup_time.isoformat() if last_cleanup_time else None
            ),
            "next_cleanup": (
                next_cleanup_time.isoformat() if next_cleanup_time else None
            ),
            # 状态信息
            "has_pending": pending_count > 0,
            "is_overdue": (
                next_cleanup_time and beijing_now > next_cleanup_time
                if next_cleanup_time
                else False
            ),
        }

    except Exception as e:
        logger.error(f"获取清理状态失败: {str(e)}", exc_info=True)

        # 返回基本配置，避免前端完全无法显示
        return {
            "enabled": Config.AUTO_CLEANUP_ENABLED,
            "retention_hours": Config.SCREENSHOT_RETENTION_HOURS,
            "interval_hours": getattr(Config, "CLEANUP_INTERVAL", 21600) / 3600,
            "cleanup_time": getattr(Config, "CLEANUP_TIME", None),
            "pending_cleanup": 0,
            "pending_size_mb": 0,
            "pending_percent": 0,
            "total_screenshots": 0,
            "total_size_mb": 0,
            "current_time": get_beijing_now().isoformat(),
            "cutoff_time": (
                get_beijing_now() - timedelta(hours=Config.SCREENSHOT_RETENTION_HOURS)
            ).isoformat(),
            "last_cleanup": None,
            "next_cleanup": None,
            "has_pending": False,
            "is_overdue": False,
            "error": str(e) if Config.DEBUG else None,
        }


# ==================== 通知相关API ====================


@app.get("/api/notifications", tags=["通知"])
def get_notifications(
    skip: int = 0,
    limit: int = 20,
    unread_first: bool = True,
    type: Optional[str] = None,
    category: Optional[str] = None,
    include_read: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取当前用户的通知列表
    """
    result = NotificationService.get_notifications(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        unread_first=unread_first,
        type=type,
        category=category,
        include_read=include_read,
    )

    return result


@app.get("/api/notifications/unread/count", tags=["通知"])
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    获取当前用户的未读通知数量
    """
    count = NotificationService.get_unread_count(db, current_user.id)
    return {"count": count}


@app.put("/api/notifications/{notification_id}/read", tags=["通知"])
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    标记通知为已读
    """
    success = NotificationService.mark_as_read(db, notification_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="通知不存在")

    return {"message": "已标记为已读"}


@app.put("/api/notifications/read-all", tags=["通知"])
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    标记所有通知为已读
    """
    count = NotificationService.mark_all_as_read(db, current_user.id)
    return {"message": f"已标记 {count} 条通知为已读"}


@app.delete("/api/notifications/{notification_id}", tags=["通知"])
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    删除单条通知
    """
    success = NotificationService.delete_notification(
        db, notification_id, current_user.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="通知不存在")

    return {"message": "通知已删除"}


@app.delete("/api/notifications/clear-all", tags=["通知"])
def clear_all_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    清空所有通知
    """
    count = NotificationService.clear_all(db, current_user.id)
    return {"message": f"已清空 {count} 条通知"}


# ==================== 工具函数 ====================


def log_activity(employee_id: str, action: str, details: dict = None):
    """记录活动日志"""
    try:
        db = next(get_db())
        activity = models.Activity(
            employee_id=employee_id, action=action, details=details
        )
        db.add(activity)
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"记录活动失败: {e}")


def create_thumbnail(image_path: str, thumbnail_path: str):
    """创建缩略图"""
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            img.thumbnail((320, 240), Image.Resampling.LANCZOS)
            img.save(thumbnail_path, "WEBP", quality=75, optimize=True)
            logger.debug(f"缩略图创建成功: {thumbnail_path}")
    except Exception as e:
        logger.error(f"创建缩略图失败: {e}")


def process_batch_upload(
    zip_path: str, client_id: str, employee_id: str, expected_count: int
):
    """处理批量上传的ZIP文件"""
    import zipfile
    from server_timezone import get_beijing_now  # 添加导入

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # ===== 修改点：解压到以北京时间命名的临时目录 =====
            extract_path = (
                STORAGE_PATH
                / "temp"
                / f"extract_{get_beijing_now().strftime('%Y%m%d_%H%M%S')}"
                # 原来是：datetime.now().strftime('%Y%m%d_%H%M%S')
            )
            # ==============================================
            extract_path.mkdir(parents=True, exist_ok=True)
            zip_ref.extractall(extract_path)

            # 处理每个文件
            count = 0
            for file_path in extract_path.glob("*"):
                if file_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    # TODO: 处理每个截图
                    count += 1

            logger.info(f"批量处理完成: {count}/{expected_count} 个文件")

            # 清理
            import shutil

            shutil.rmtree(extract_path)

        # 删除ZIP文件
        Path(zip_path).unlink()

    except Exception as e:
        logger.error(f"批量处理失败: {e}")


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str


class RegenerateApiKeySchema(BaseModel):
    pass  # 不需要参数


@app.post("/api/auth/change-password", tags=["认证"])
def change_password(
    password_data: ChangePasswordSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """修改当前用户密码"""

    # 1️⃣ 验证当前密码
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码错误"
        )

    # 2️⃣ 验证新密码长度
    if len(password_data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="新密码至少需要6个字符"
        )

    # 3️⃣ 新密码不能与旧密码相同
    if verify_password(password_data.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与旧密码相同"
        )

    try:
        # 4️⃣ 更新密码
        current_user.password_hash = get_password_hash(password_data.new_password)

        # 5️⃣ 记录密码修改时间（用于 token 失效）
        if hasattr(current_user, "password_changed_at"):
            current_user.password_changed_at = get_utc_now()

        db.commit()
        db.refresh(current_user)

    except Exception as e:
        db.rollback()
        logger.error(f"密码修改失败: {current_user.username}, error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="密码修改失败，请重试",
        )

    logger.info(f"用户密码已修改: {current_user.username}")

    # 6️⃣ 生成新 token（保持你原有逻辑）
    access_token_expires = timedelta(minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.username, "role": current_user.role},
        expires_delta=access_token_expires,
    )

    return {
        "message": "密码修改成功",
        "access_token": access_token,
        "token_type": "bearer",
        "username": current_user.username,
        "role": current_user.role,
    }


@app.post("/api/auth/regenerate-api-key", tags=["认证"])
def regenerate_api_key(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """重新生成API密钥"""
    import secrets

    # 生成新的API密钥
    new_api_key = f"sk-" + secrets.token_urlsafe(32)

    # 这里需要根据你的实际存储方式保存API密钥
    # 例如保存到数据库的 SystemConfig 表
    from server_config_manager import set_config

    set_config(
        key="api_key",
        value=new_api_key,
        category="security",
        description="API密钥",
        user_id=current_user.id,
    )

    logger.info(f"API密钥已重新生成: {current_user.username}")

    return {"api_key": new_api_key}


@app.get("/api/debug/file/{path:path}", tags=["调试"])
async def debug_file_access(path: str):
    """调试接口：检查文件访问"""

    result = {"requested_path": path, "checks": [], "found": False}

    # 可能的根目录
    root_paths = [
        Path(Config.SCREENSHOT_DIR),
        Path("/data/screenshots"),
        Path.cwd() / "screenshots",
        Path.cwd(),
    ]

    for root in root_paths:
        if not root.exists():
            result["checks"].append(
                {"root": str(root), "exists": False, "message": "目录不存在"}
            )
            continue

        # 尝试直接拼接
        file_path = root / path
        resolved = file_path.resolve()

        check = {
            "root": str(root),
            "root_exists": True,
            "attempted_path": str(file_path),
            "resolved_path": str(resolved),
            "exists": resolved.exists(),
            "is_file": resolved.is_file() if resolved.exists() else False,
            "size": (
                resolved.stat().st_size
                if resolved.exists() and resolved.is_file()
                else None
            ),
            "readable": os.access(resolved, os.R_OK) if resolved.exists() else False,
        }

        # 尝试添加 screenshots 前缀
        if not path.startswith("screenshots/"):
            alt_path = root / "screenshots" / path
            alt_resolved = alt_path.resolve()
            check["alt_path"] = str(alt_path)
            check["alt_exists"] = alt_resolved.exists()

        result["checks"].append(check)

        if check["exists"] and check["is_file"]:
            result["found"] = True
            result["found_at"] = str(resolved)

    return result


@app.get("/api/debug/check-files", tags=["调试"])
def check_files_existence(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """检查数据库中的文件是否实际存在"""

    # 获取最近的截图
    screenshots = (
        db.query(models.Screenshot)
        .order_by(models.Screenshot.screenshot_time.desc())
        .limit(limit)
        .all()
    )

    result = {
        "total_checked": len(screenshots),
        "existing": [],
        "missing": [],
        "storage_path": str(STORAGE_PATH),
    }

    for ss in screenshots:
        file_path = STORAGE_PATH / ss.filename
        exists = file_path.exists()

        item = {
            "id": ss.id,
            "filename": ss.filename,
            "storage_url": ss.storage_url,
            "screenshot_time": (
                ss.screenshot_time.isoformat() if ss.screenshot_time else None
            ),
            "file_path": str(file_path),
            "exists": exists,
            "file_size": file_path.stat().st_size if exists else None,
        }

        if exists:
            result["existing"].append(item)
        else:
            result["missing"].append(item)

    result["existing_count"] = len(result["existing"])
    result["missing_count"] = len(result["missing"])

    return result


@app.get("/api/debug/file-stats", tags=["调试"])
def get_file_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取文件系统统计信息"""

    # 数据库中的记录数
    db_count = db.query(models.Screenshot).count()

    # 文件系统中的文件数
    webp_files = list(STORAGE_PATH.glob("**/*.webp"))
    jpg_files = list(STORAGE_PATH.glob("**/*.jpg"))
    png_files = list(STORAGE_PATH.glob("**/*.png"))

    fs_count = len(webp_files) + len(jpg_files) + len(png_files)

    # 计算总大小
    total_size = 0
    for f in STORAGE_PATH.glob("**/*.*"):
        if f.is_file():
            total_size += f.stat().st_size

    return {
        "database": {"screenshot_records": db_count},
        "filesystem": {
            "total_files": fs_count,
            "webp_files": len(webp_files),
            "jpg_files": len(jpg_files),
            "png_files": len(png_files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "storage_path": str(STORAGE_PATH),
        },
        "difference": db_count - fs_count,
        "status": "ok" if db_count == fs_count else "inconsistent",
    }


# ==================== 辅助函数：统一格式化 ====================
def format_screenshot_response(row_dict):
    """
    统一格式化截图响应 - 修复URL路径问题
    确保所有截图接口返回相同的字段结构
    """
    st = row_dict.get("screenshot_time")

    # ===== 🚨 关键修复：确保URL以 /screenshots/ 开头 =====
    storage_url = row_dict.get("storage_url")
    if storage_url and not storage_url.startswith("/screenshots/"):
        # 如果storage_url不正确，从filename构建
        filename = row_dict.get("filename")
        if filename:
            storage_url = f"/screenshots/{filename}"
        else:
            storage_url = None

    thumbnail = row_dict.get("thumbnail")
    if thumbnail and not thumbnail.startswith("/screenshots/"):
        thumbnail = f"/screenshots/{thumbnail}"

    # =================================================

    return {
        # 基础字段
        "id": row_dict.get("id"),
        "employee_id": row_dict.get("employee_id"),
        "name": row_dict.get("employee_name") or row_dict.get("employee_id"),
        "client_id": row_dict.get("client_id"),
        "filename": row_dict.get("filename"),
        "thumbnail": thumbnail,  # ✅ 修复后的缩略图URL
        "file_size": row_dict.get("file_size"),
        "width": row_dict.get("width"),
        "height": row_dict.get("height"),
        "storage_url": storage_url,  # ✅ 修复后的原图URL
        "uploaded_at": (
            row_dict.get("uploaded_at").isoformat()
            if row_dict.get("uploaded_at")
            else None
        ),
        "screenshot_time": st.isoformat() if st else None,
        "computer_name": row_dict.get("computer_name"),
        "windows_user": row_dict.get("windows_user"),
        "image_format": row_dict.get("image_format"),
        "is_encrypted": row_dict.get("is_encrypted"),
        # 派生字段
        "url": storage_url,  # ✅ 使用修复后的URL
        "time": st.strftime("%H:%M:%S") if st else None,
        "date": st.strftime("%Y-%m-%d") if st else None,
        "datetime": st.strftime("%Y-%m-%d %H:%M:%S") if st else None,
        "size_str": format_file_size_util(row_dict.get("file_size")),
        "format": row_dict.get("image_format"),
        "encrypted": row_dict.get("is_encrypted"),
        # 时区标识
        "timezone": "Asia/Shanghai",
    }


def format_file_size_util(size: int) -> str:
    """统一文件大小格式化工具"""
    if not size:
        return "0 B"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size/1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size/(1024*1024):.1f} MB"
    return f"{size/(1024*1024*1024):.1f} GB"


def format_employee_dict(employee):
    """统一格式化员工字典"""
    return (
        employee.to_dict()
        if hasattr(employee, "to_dict")
        else {
            "id": getattr(employee, "employee_id", None),
            "name": getattr(employee, "name", None),
            "department": getattr(employee, "department", None),
            "position": getattr(employee, "position", None),
            "status": getattr(employee, "status", None),
            "email": getattr(employee, "email", None),
            "phone": getattr(employee, "phone", None),
            "today_screenshots": getattr(employee, "today_screenshots", 0),
            "total_screenshots": getattr(employee, "total_screenshots", 0),
            "last_active": (
                employee.last_active.isoformat()
                if hasattr(employee, "last_active") and employee.last_active
                else None
            ),
            "is_online": getattr(employee, "has_active_clients", False),
        }
    )


def format_client_dict(client):
    """统一格式化客户端字典"""
    return (
        client.to_dict()
        if hasattr(client, "to_dict")
        else {
            "client_id": getattr(client, "client_id", None),
            "employee_id": getattr(client, "employee_id", None),
            "computer_name": getattr(client, "computer_name", None),
            "windows_user": getattr(client, "windows_user", None),
            "ip_address": getattr(client, "ip_address", None),
            "mac_address": getattr(client, "mac_address", None),
            "os_version": getattr(client, "os_version", None),
            "client_version": getattr(client, "client_version", None),
            "last_seen": (
                client.last_seen.isoformat()
                if hasattr(client, "last_seen") and client.last_seen
                else None
            ),
            "is_online": getattr(client, "is_online", False),
            "config": getattr(client, "config", {}),
            "capabilities": getattr(client, "capabilities", []),
        }
    )


app.include_router(remote_screen_router)


# ==================== 静态文件服务 ====================

# 1. 截图目录处理（方案3 - StaticFiles）
screenshots_path = Path(Config.SCREENSHOT_DIR)
logger.info(f"配置的截图目录: {screenshots_path}")

# 确保截图目录存在
try:
    screenshots_path.mkdir(parents=True, exist_ok=True)
except Exception as e:
    logger.error(f"创建截图目录失败: {e}")

# 检查主目录
if screenshots_path.exists():
    # 确保缩略图目录存在
    thumbnails_path = screenshots_path / "thumbnails"
    thumbnails_path.mkdir(parents=True, exist_ok=True)

    # 挂载 StaticFiles（方案3）
    try:
        app.mount(
            "/screenshots",
            StaticFiles(directory=str(screenshots_path)),
            name="screenshots",
        )
        logger.info(f"✅ 截图目录已挂载: /screenshots -> {screenshots_path}")
        logger.info(f"   ✅ 无缓存限制，可访问所有历史图片")

        # 调试信息
        webp_files = list(screenshots_path.glob("**/*.webp"))
        logger.info(f"找到 {len(webp_files)} 个 .webp 文件")
        if webp_files:
            sample_files = webp_files[:5]
            logger.info(
                f"示例截图路径: {[str(f.relative_to(screenshots_path)) for f in sample_files]}"
            )
    except Exception as e:
        logger.error(f"❌ StaticFiles 挂载失败: {e}")
        # 如果挂载失败，使用备用方案（自定义路由，但无缓存）
        logger.info("使用备用文件服务方案...")

        @app.get("/screenshots/{path:path}", tags=["文件"])
        async def serve_screenshot_fallback(path: str):
            """备用截图服务 - 无缓存版本"""
            if not path or ".." in path or path.startswith("/"):
                raise HTTPException(status_code=400, detail="Invalid file path")

            path = path.replace("\\", "/")
            full_path = (screenshots_path / path).resolve()

            if (
                str(full_path).startswith(str(screenshots_path))
                and full_path.exists()
                and full_path.is_file()
            ):
                media_type, _ = mimetypes.guess_type(str(full_path))
                return FileResponse(
                    full_path,
                    media_type=media_type or "application/octet-stream",
                    headers={"Cache-Control": "public, max-age=3600"},
                )

            raise HTTPException(status_code=404, detail="File not found")

else:
    # 备选方案
    alt_screenshots_path = Path.cwd() / "screenshots"
    alt_screenshots_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"使用备用截图目录: {alt_screenshots_path}")
    try:
        app.mount(
            "/screenshots",
            StaticFiles(directory=str(alt_screenshots_path)),
            name="screenshots",
        )
        logger.info(f"✅ 备用截图目录已挂载: /screenshots -> {alt_screenshots_path}")

        # 更新全局变量，供其他函数使用
        screenshots_path = alt_screenshots_path
    except Exception as e:
        logger.error(f"❌ 备用目录挂载失败: {e}")

# 2. 静态资源目录（如assets）
assets_dir = Path.cwd() / "assets"
if assets_dir.exists():
    try:
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        logger.info(f"✅ 静态资源目录已挂载: /assets")
    except Exception as e:
        logger.error(f"❌ 静态资源目录挂载失败: {e}")
else:
    logger.info("静态资源目录不存在，跳过挂载")

# 3. 前端路由处理
index_path = Path.cwd() / "index.html"
if not index_path.exists():
    # 尝试在 dist 目录中查找
    dist_index = Path.cwd() / "dist" / "index.html"
    if dist_index.exists():
        index_path = dist_index
        logger.info(f"在 dist 目录找到 index.html: {index_path}")


@app.get("/")
async def serve_root():
    """根路径返回 index.html"""
    if index_path.exists():
        return FileResponse(index_path)
    logger.error("❌ index.html 不存在")
    return {"error": "Frontend not found", "status": "index.html missing"}, 404


# ==================== 可选：文件系统健康检查 ====================


@app.get("/api/health/filesystem", tags=["系统"])
async def check_filesystem_health():
    """检查文件系统健康状态"""
    result = {
        "screenshots_directory": {
            "path": str(screenshots_path),
            "exists": screenshots_path.exists(),
            "writable": (
                os.access(str(screenshots_path), os.W_OK)
                if screenshots_path.exists()
                else False
            ),
            "file_count": len(list(screenshots_path.glob("**/*.*"))),
        },
        "index_file": {
            "path": str(index_path),
            "exists": index_path.exists(),
        },
    }

    # 检查最近的文件（用于验证）
    try:
        recent_files = list(screenshots_path.glob("**/*.webp"))[:5]
        result["screenshots_directory"]["recent_files"] = [
            str(f.relative_to(screenshots_path)) for f in recent_files
        ]
    except Exception as e:
        result["screenshots_directory"]["recent_files_error"] = str(e)

    return result


def fix_screenshot_urls(db_session):
    """修复数据库中可能错误的截图URL"""
    from server_models import Screenshot

    screenshots = db_session.query(Screenshot).all()
    fixed_count = 0

    for ss in screenshots:
        # 正确的URL格式应该是 /screenshots/路径
        correct_url = f"/screenshots/{ss.filename}"

        if ss.storage_url != correct_url:
            old_url = ss.storage_url
            ss.storage_url = correct_url
            fixed_count += 1
            logger.debug(f"修复截图 {ss.id} URL: {old_url} -> {correct_url}")

    if fixed_count > 0:
        db_session.commit()
        logger.info(f"✅ 已修复 {fixed_count} 个截图的URL")

    return fixed_count


# ==================== 浏览器历史接口 ====================
@app.post("/api/browser/history", tags=["监控"])
async def upload_browser_history(
    history: List[schemas.BrowserHistoryCreate],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    上传浏览器历史记录
    - 客户端批量上传
    - 自动关联员工和客户端
    """
    logger.info(f"📊 收到浏览器历史上传: {len(history)} 条记录")

    if history:
        logger.info(f"第一条数据: {history[0]}")
        logger.info(f"数据类型: {type(history[0].visit_time)}")

    saved_count = 0
    for item in history:
        try:
            # 验证客户端是否存在
            if item.client_id:
                client = (
                    db.query(models.Client)
                    .filter(models.Client.client_id == item.client_id)
                    .first()
                )
                if client:
                    client.last_seen = get_beijing_now()

            # 创建记录
            db_history = models.BrowserHistory(**item.dict())
            db.add(db_history)
            saved_count += 1

        except Exception as e:
            logger.error(f"保存浏览器历史失败: {e}")

    if saved_count > 0:
        db.commit()
        logger.info(f"✅ 已保存 {saved_count} 条浏览器历史")

    return {"status": "ok", "saved": saved_count}


# ==================== 浏览器历史接口 ====================


@app.get("/api/browser/history", tags=["监控"])
def get_browser_history(
    employee_id: Optional[str] = None,
    client_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    browser: Optional[str] = None,  # ✅ 这个参数已经存在
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取浏览器历史记录 - 修复浏览器筛选"""
    from server_timezone import parse_beijing_datetime, to_utc_time, make_naive
    from sqlalchemy import or_

    query = db.query(models.BrowserHistory)

    if employee_id:
        query = query.filter(models.BrowserHistory.employee_id == employee_id)

    if client_id:
        query = query.filter(models.BrowserHistory.client_id == client_id)

    # ✅ 修复：浏览器筛选逻辑
    if browser:
        if browser == "other":
            # 其他浏览器：不是 chrome、edge、firefox 的
            query = query.filter(
                ~models.BrowserHistory.browser.in_(["chrome", "edge", "firefox"])
            )
        else:
            # 精确匹配浏览器名称
            query = query.filter(models.BrowserHistory.browser == browser)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.BrowserHistory.url.ilike(search_term),
                models.BrowserHistory.title.ilike(search_term),
            )
        )

    if start_date:
        beijing_start = parse_beijing_datetime(f"{start_date} 00:00:00")
        utc_start = to_utc_time(beijing_start)
        query = query.filter(models.BrowserHistory.visit_time >= utc_start)

    if end_date:
        beijing_end = parse_beijing_datetime(f"{end_date} 23:59:59")
        utc_end = to_utc_time(beijing_end)
        query = query.filter(models.BrowserHistory.visit_time <= utc_end)

    total = query.count()
    items = (
        query.order_by(models.BrowserHistory.visit_time.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "items": [item.to_dict() for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total,
    }


# server_main.py - 修改浏览器统计接口


@app.get("/api/browser/stats", tags=["监控"])
def get_browser_stats(
    employee_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    browser: Optional[str] = None,  # ✅ 添加 browser 参数
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取浏览器使用统计 - 修复浏览器筛选"""
    from server_timezone import parse_beijing_datetime, to_utc_time, make_naive
    from sqlalchemy import func

    query = db.query(
        models.BrowserHistory.browser,
        func.count(models.BrowserHistory.id).label("visits"),
        func.sum(models.BrowserHistory.duration).label("total_duration"),
    )

    if employee_id:
        query = query.filter(models.BrowserHistory.employee_id == employee_id)

    # ✅ 添加浏览器筛选
    if browser:
        if browser == "other":
            query = query.filter(
                ~models.BrowserHistory.browser.in_(["chrome", "edge", "firefox"])
            )
        else:
            query = query.filter(models.BrowserHistory.browser == browser)

    if start_date:
        beijing_start = parse_beijing_datetime(f"{start_date} 00:00:00")
        utc_start = to_utc_time(beijing_start)
        query = query.filter(models.BrowserHistory.visit_time >= utc_start)

    if end_date:
        beijing_end = parse_beijing_datetime(f"{end_date} 23:59:59")
        utc_end = to_utc_time(beijing_end)
        query = query.filter(models.BrowserHistory.visit_time <= utc_end)

    results = query.group_by(models.BrowserHistory.browser).all()

    stats = []
    for r in results:
        stats.append(
            {
                "browser": r[0] or "unknown",
                "visits": r[1],
                "total_minutes": round((r[2] or 0) / 60, 1),
            }
        )

    return {"items": stats, "total": len(stats)}


# ==================== 软件使用接口 ====================
@app.post("/api/apps/usage", tags=["监控"])
async def upload_app_usage(
    usage: List[schemas.AppUsageCreate],
    db: Session = Depends(get_db),
):
    """上传软件使用记录"""
    logger.info(f"📱 收到软件使用上传: {len(usage)} 条记录")

    saved_count = 0
    for item in usage:
        try:
            db_usage = models.AppUsage(**item.dict())
            db.add(db_usage)
            saved_count += 1
        except Exception as e:
            logger.error(f"保存软件使用失败: {e}")

    if saved_count > 0:
        db.commit()
        logger.info(f"✅ 已保存 {saved_count} 条软件使用")

    return {"status": "ok", "saved": saved_count}


# ==================== 软件使用接口 ====================
@app.get("/api/apps/usage", tags=["监控"])
def get_app_usage(
    employee_id: Optional[str] = None,
    client_id: Optional[str] = None,
    app_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    foreground_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取软件使用记录"""
    from server_timezone import parse_beijing_datetime, to_utc_time, make_naive

    query = db.query(models.AppUsage)

    if employee_id:
        query = query.filter(models.AppUsage.employee_id == employee_id)

    if client_id:
        query = query.filter(models.AppUsage.client_id == client_id)

    if app_name:
        query = query.filter(models.AppUsage.app_name.ilike(f"%{app_name}%"))

    if foreground_only:
        query = query.filter(models.AppUsage.is_foreground == True)

    if start_date:
        beijing_start = parse_beijing_datetime(f"{start_date} 00:00:00")
        utc_start = to_utc_time(beijing_start)
        query = query.filter(models.AppUsage.start_time >= utc_start)

    if end_date:
        beijing_end = parse_beijing_datetime(f"{end_date} 23:59:59")
        utc_end = to_utc_time(beijing_end)
        query = query.filter(models.AppUsage.start_time <= utc_end)

    total = query.count()
    items = (
        query.order_by(models.AppUsage.start_time.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "items": [item.to_dict() for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total,
    }


@app.get("/api/apps/stats", tags=["监控"])
def get_app_stats(
    employee_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "app",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取软件使用统计"""
    from server_timezone import parse_beijing_datetime, to_utc_time, make_naive
    from sqlalchemy import func, cast, Date

    if group_by == "date":
        query = db.query(
            cast(models.AppUsage.start_time, Date).label("date"),
            func.count(models.AppUsage.id).label("sessions"),
            func.sum(models.AppUsage.duration).label("total_duration"),
        )
        if employee_id:
            query = query.filter(models.AppUsage.employee_id == employee_id)
        if start_date:
            beijing_start = parse_beijing_datetime(f"{start_date} 00:00:00")
            utc_start = to_utc_time(beijing_start)
            query = query.filter(models.AppUsage.start_time >= utc_start)
        if end_date:
            beijing_end = parse_beijing_datetime(f"{end_date} 23:59:59")
            utc_end = to_utc_time(beijing_end)
            query = query.filter(models.AppUsage.start_time <= utc_end)
        results = query.group_by(cast(models.AppUsage.start_time, Date)).all()

        stats = []
        for r in results:
            stats.append(
                {
                    "date": r[0].isoformat() if r[0] else None,
                    "sessions": r[1],
                    "total_minutes": round((r[2] or 0) / 60, 1),
                }
            )
        return {"items": stats, "total": len(stats)}

    # 默认按应用分组
    query = db.query(
        models.AppUsage.app_name,
        func.count(models.AppUsage.id).label("sessions"),
        func.sum(models.AppUsage.duration).label("total_duration"),
        func.avg(models.AppUsage.cpu_avg).label("avg_cpu"),
        func.avg(models.AppUsage.memory_avg).label("avg_memory"),
    )

    if employee_id:
        query = query.filter(models.AppUsage.employee_id == employee_id)

    if start_date:
        beijing_start = parse_beijing_datetime(f"{start_date} 00:00:00")
        utc_start = to_utc_time(beijing_start)
        query = query.filter(models.AppUsage.start_time >= utc_start)

    if end_date:
        beijing_end = parse_beijing_datetime(f"{end_date} 23:59:59")
        utc_end = to_utc_time(beijing_end)
        query = query.filter(models.AppUsage.start_time <= utc_end)

    results = query.group_by(models.AppUsage.app_name).all()

    stats = []
    for r in results:
        stats.append(
            {
                "app_name": r[0],
                "sessions": r[1],
                "total_minutes": round((r[2] or 0) / 60, 1),
                "avg_cpu": round(r[3] or 0, 1),
                "avg_memory_mb": round(r[4] or 0, 1),
            }
        )

    return {"items": stats, "total": len(stats)}


# ==================== 文件操作接口 ====================
@app.post("/api/files/operations", tags=["监控"])
async def upload_file_operations(
    operations: List[schemas.FileOperationCreate],
    db: Session = Depends(get_db),
):
    """上传文件操作记录"""
    logger.info(f"📁 收到文件操作上传: {len(operations)} 条记录")

    saved_count = 0
    for item in operations:
        try:
            db_op = models.FileOperation(**item.dict())
            db.add(db_op)
            saved_count += 1
        except Exception as e:
            logger.error(f"保存文件操作失败: {e}")

    if saved_count > 0:
        db.commit()
        logger.info(f"✅ 已保存 {saved_count} 条文件操作")

    return {"status": "ok", "saved": saved_count}


# ==================== 文件操作接口 ====================
@app.get("/api/files/operations", tags=["监控"])
def get_file_operations(
    employee_id: Optional[str] = None,
    client_id: Optional[str] = None,
    operation: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    file_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取文件操作记录"""
    from server_timezone import parse_beijing_datetime, to_utc_time, make_naive

    query = db.query(models.FileOperation)

    if employee_id:
        query = query.filter(models.FileOperation.employee_id == employee_id)

    if client_id:
        query = query.filter(models.FileOperation.client_id == client_id)

    if operation:
        query = query.filter(models.FileOperation.operation == operation)

    if file_type:
        query = query.filter(models.FileOperation.file_type == file_type)

    if start_date:
        beijing_start = parse_beijing_datetime(f"{start_date} 00:00:00")
        utc_start = to_utc_time(beijing_start)
        query = query.filter(models.FileOperation.operation_time >= utc_start)

    if end_date:
        beijing_end = parse_beijing_datetime(f"{end_date} 23:59:59")
        utc_end = to_utc_time(beijing_end)
        query = query.filter(models.FileOperation.operation_time <= utc_end)

    total = query.count()
    items = (
        query.order_by(models.FileOperation.operation_time.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "items": [item.to_dict() for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total,
    }


@app.get("/api/files/stats", tags=["监控"])
def get_file_stats(
    employee_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """获取文件操作统计"""
    from sqlalchemy import func

    # 按操作类型统计
    stats = db.query(
        models.FileOperation.operation,
        func.count(models.FileOperation.id).label("count"),
    )

    if employee_id:
        stats = stats.filter(models.FileOperation.employee_id == employee_id)

    if start_date:
        from server_timezone import parse_beijing_datetime, to_utc_time

        beijing_start = parse_beijing_datetime(f"{start_date} 00:00:00")
        utc_start = to_utc_time(beijing_start)
        stats = stats.filter(models.FileOperation.operation_time >= utc_start)

    if end_date:
        from server_timezone import parse_beijing_datetime, to_utc_time

        beijing_end = parse_beijing_datetime(f"{end_date} 23:59:59")
        utc_end = to_utc_time(beijing_end)
        stats = stats.filter(models.FileOperation.operation_time <= utc_end)

    results = stats.group_by(models.FileOperation.operation).all()

    # 按文件类型统计
    type_stats = db.query(
        models.FileOperation.file_type,
        func.count(models.FileOperation.id).label("count"),
    )

    if employee_id:
        type_stats = type_stats.filter(models.FileOperation.employee_id == employee_id)

    if start_date:
        type_stats = type_stats.filter(models.FileOperation.operation_time >= utc_start)

    if end_date:
        type_stats = type_stats.filter(models.FileOperation.operation_time <= utc_end)

    type_results = (
        type_stats.filter(models.FileOperation.file_type.isnot(None))
        .group_by(models.FileOperation.file_type)
        .limit(20)
        .all()
    )

    return {
        "by_operation": [
            {
                "operation": r[0],
                "operation_cn": models.FileOperation._get_operation_cn(r[0]),
                "count": r[1],
            }
            for r in results
        ],
        "by_file_type": [{"type": r[0] or "其他", "count": r[1]} for r in type_results],
    }


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """处理所有前端路由（SPA支持）"""

    # 跳过API路径
    # if full_path.startswith("api/"):
    #     return {"error": "Resource not found"}, 404

    # 跳过截图路径（由 StaticFiles 处理）
    if full_path.startswith("screenshots/"):
        return {"error": "Resource not found"}, 404

    # 跳过 assets 路径（由 StaticFiles 处理）
    if full_path.startswith("assets/"):
        return {"error": "Resource not found"}, 404

    # 检查是否是静态文件
    static_extensions = (
        ".js",
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".webp",
    )

    if any(full_path.endswith(ext) for ext in static_extensions):
        # 先检查当前目录
        file_path = Path.cwd() / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # 再检查 dist 目录
        dist_path = Path.cwd() / "dist" / full_path
        if dist_path.exists() and dist_path.is_file():
            return FileResponse(dist_path)

        logger.debug(f"静态文件不存在: {full_path}")

    # 其他所有路径返回 index.html（SPA路由）
    if index_path.exists():
        return FileResponse(index_path)

    return {"error": "Frontend not found"}, 404


from fastapi import Depends


@app.post("/api/debug/unify-paths", tags=["调试"])
def unify_paths(db: Session = Depends(get_db)):
    """
    统一所有路径格式 - 全面修复
    功能：
    1. 检查所有员工ID格式
    2. 修复截图文件名中的路径
    3. 确保数据库记录与实际文件一致
    """
    from pathlib import Path
    import shutil

    logger.info("=" * 50)
    logger.info("🔧 开始统一路径修复")
    logger.info("=" * 50)

    result = {
        "employees_checked": 0,
        "employees_fixed": 0,
        "screenshots_checked": 0,
        "screenshots_fixed": 0,
        "files_moved": 0,
        "errors": [],
    }

    try:
        # ===== 1. 检查并修复员工ID =====
        logger.info("📋 检查员工ID格式...")
        employees = db.query(models.Employee).all()
        result["employees_checked"] = len(employees)

        for emp in employees:
            old_id = emp.employee_id

            # 如果ID包含8位UUID后缀
            if "_" in old_id and len(old_id.split("_")[-1]) == 8:
                # 生成不带后缀的新ID
                new_id = "_".join(old_id.split("_")[:-1])

                # 检查新ID是否已存在
                existing = (
                    db.query(models.Employee)
                    .filter(models.Employee.employee_id == new_id)
                    .first()
                )

                if not existing:
                    logger.info(f"修复员工ID: {old_id} -> {new_id}")

                    # 更新员工表
                    emp.employee_id = new_id

                    # 更新关联的截图
                    for ss in emp.screenshots:
                        if ss.filename:
                            old_filename = ss.filename
                            new_filename = old_filename.replace(old_id, new_id)
                            ss.filename = new_filename
                            ss.storage_url = f"/screenshots/{new_filename}"

                            # 尝试移动实际文件
                            old_path = STORAGE_PATH / old_filename
                            new_path = STORAGE_PATH / new_filename
                            if old_path.exists() and not new_path.exists():
                                new_path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(str(old_path), str(new_path))
                                result["files_moved"] += 1
                                logger.debug(
                                    f"移动文件: {old_filename} -> {new_filename}"
                                )

                    # 更新关联的客户端
                    for client in emp.clients:
                        client.employee_id = new_id

                    result["employees_fixed"] += 1

        # ===== 2. 检查并修复截图路径 =====
        logger.info("📋 检查截图路径...")
        screenshots = db.query(models.Screenshot).all()
        result["screenshots_checked"] = len(screenshots)

        for ss in screenshots:
            if not ss.filename:
                continue

            # 检查文件是否存在
            file_path = STORAGE_PATH / ss.filename

            if not file_path.exists():
                logger.debug(f"文件不存在: {ss.filename}")

                # 尝试查找可能的文件
                parent_dir = file_path.parent
                if parent_dir.exists():
                    # 查找文件名相似的图片
                    possible_files = list(parent_dir.glob("*.webp")) + list(
                        parent_dir.glob("*.jpg")
                    )

                    if possible_files:
                        # 使用找到的第一个文件
                        found_file = possible_files[0]
                        rel_path = found_file.relative_to(STORAGE_PATH)

                        logger.info(f"修复截图 {ss.id}: {ss.filename} -> {rel_path}")

                        ss.filename = str(rel_path)
                        ss.storage_url = f"/screenshots/{rel_path}"
                        result["screenshots_fixed"] += 1

                        # 如果文件名包含 _thumb，但找到的文件没有，更新缩略图字段
                        if "_thumb" in str(rel_path):
                            ss.thumbnail = str(rel_path)
                    else:
                        # 尝试在上级目录查找
                        for root in [STORAGE_PATH, STORAGE_PATH / "thumbnails"]:
                            if root.exists():
                                all_files = list(root.rglob("*.webp"))
                                # 根据截图时间匹配
                                if ss.screenshot_time:
                                    time_str = ss.screenshot_time.strftime("%H-%M-%S")
                                    matching = [
                                        f for f in all_files if time_str in f.name
                                    ]
                                    if matching:
                                        rel_path = matching[0].relative_to(STORAGE_PATH)
                                        ss.filename = str(rel_path)
                                        ss.storage_url = f"/screenshots/{rel_path}"
                                        result["screenshots_fixed"] += 1
                                        break

        # ===== 3. 检查缩略图 =====
        logger.info("📋 检查缩略图...")
        thumb_count = 0
        for ss in screenshots:
            if ss.thumbnail:
                thumb_path = STORAGE_PATH / ss.thumbnail
                if not thumb_path.exists() and ss.filename:
                    # 尝试生成缩略图路径
                    base = ss.filename.rsplit(".", 1)[0]
                    possible_thumb = f"{base}_thumb.webp"
                    if (STORAGE_PATH / possible_thumb).exists():
                        ss.thumbnail = possible_thumb
                        thumb_count += 1

        if thumb_count > 0:
            logger.info(f"修复 {thumb_count} 个缩略图路径")

        # ===== 4. 提交所有更改 =====
        if result["employees_fixed"] > 0 or result["screenshots_fixed"] > 0:
            db.commit()
            logger.info(f"✅ 已提交所有更改到数据库")

        # ===== 5. 统计结果 =====
        logger.info("=" * 50)
        logger.info("📊 修复结果统计:")
        logger.info(f"   - 检查员工: {result['employees_checked']}")
        logger.info(f"   - 修复员工: {result['employees_fixed']}")
        logger.info(f"   - 检查截图: {result['screenshots_checked']}")
        logger.info(f"   - 修复截图: {result['screenshots_fixed']}")
        logger.info(f"   - 移动文件: {result['files_moved']}")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"修复过程中出错: {e}", exc_info=True)
        result["errors"].append(str(e))
        db.rollback()

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server_main:app", host="0.0.0.0", port=8000, reload=Config.DEBUG)
