# server_config.py - 修正版
"""
服务器配置模块
优先级: 数据库配置 > 环境变量 > 默认值
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# 延迟导入，避免循环引用
_config_manager = None


def get_config_manager():
    """延迟获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        from server_config_manager import config_manager

        _config_manager = config_manager
    return _config_manager


load_dotenv()

# 配置日志
logger = logging.getLogger(__name__)


class Config:
    # ========== 基础配置 ==========
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())

    # ========== 数据库配置（只从环境变量读取）==========
    PRIMARY_DATABASE_URL = os.environ.get("DATABASE_URL")
    if not PRIMARY_DATABASE_URL:
        raise ValueError("生产环境必须设置 DATABASE_URL 环境变量")

    BACKUP_DATABASE_URL = os.environ.get("BACKUP_DATABASE_URL")
    CA_CERT_PATH = os.environ.get("CA_CERT_PATH", "./ca.pem")

    # ========== JWT配置 ==========
    ALGORITHM = "HS256"

    @classmethod
    def _get_db_config(cls, key, env_var, default, converter=None):
        """从数据库获取配置，失败时回退到环境变量"""
        try:
            manager = get_config_manager()
            value = manager.get(key)
            if value is not None:
                return value
        except Exception as e:
            logger.debug(f"从数据库获取配置 {key} 失败: {e}")

        # 回退到环境变量
        env_value = os.environ.get(env_var, default)
        if converter:
            return converter(env_value)
        return env_value

    # ========== 动态配置（优先从数据库读取）==========

    @classmethod
    @property
    def ACCESS_TOKEN_EXPIRE_MINUTES(cls):
        """JWT过期时间（分钟）"""
        return cls._get_db_config(
            "jwt_expire_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES", "480", int
        )

    # ========== 存储配置 ==========

    @classmethod
    @property
    def SCREENSHOT_DIR(cls):
        """截图存储路径"""
        return cls._get_db_config(
            "screenshot_dir", "SCREENSHOT_DIR", "/data/screenshots"
        )

    @classmethod
    @property
    def SCREENSHOT_FORMAT(cls):
        """图片格式"""
        return cls._get_db_config(
            "screenshot_format", "SCREENSHOT_FORMAT", "webp"
        ).lower()

    @classmethod
    @property
    def SCREENSHOT_QUALITY(cls):
        """图片质量"""
        return cls._get_db_config("screenshot_quality", "SCREENSHOT_QUALITY", "80", int)

    @classmethod
    @property
    def SCREENSHOT_INTERVAL(cls):
        """截图间隔（秒）"""
        return cls._get_db_config(
            "screenshot_interval", "SCREENSHOT_INTERVAL", "60", int
        )

    # ========== 自动清理配置 ==========

    @classmethod
    @property
    def AUTO_CLEANUP_ENABLED(cls):
        """自动清理开关"""
        value = cls._get_db_config(
            "auto_cleanup_enabled", "AUTO_CLEANUP_ENABLED", "true"
        )
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"

    @classmethod
    @property
    def SCREENSHOT_RETENTION_HOURS(cls):
        """截图保留时间（小时）"""
        return cls._get_db_config(
            "screenshot_retention_hours", "SCREENSHOT_RETENTION_HOURS", "4", int
        )

    @classmethod
    @property
    def CLEANUP_INTERVAL(cls):
        """清理间隔（秒）"""
        return cls._get_db_config("cleanup_interval", "CLEANUP_INTERVAL", "21600", int)

    # ========== 管理员账号（只从环境变量读取，安全考虑）==========
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
    if not ADMIN_PASSWORD:
        raise ValueError("生产环境必须设置 ADMIN_PASSWORD 环境变量")

    # ========== Redis配置 ==========
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # ========== 固定配置（不需要动态修改）==========

    # 缩略图配置
    THUMBNAIL_SIZE = (320, 240)
    THUMBNAIL_QUALITY = 75

    # 上传限制
    MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", "20")) * 1024 * 1024
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp"}

    # 性能配置
    MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "4"))
    REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))
    GUNICORN_WORKERS = int(os.environ.get("GUNICORN_WORKERS", "2"))
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")

    # 数据库连接池配置
    DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "20"))
    DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "300"))

    # ========== 兼容原有调用方式 ==========
    # 这些属性保持原样，让旧代码可以继续工作

    @classmethod
    def get(cls, key, default=None):
        """兼容旧代码的get方法"""
        if hasattr(cls, key):
            return getattr(cls, key)
        return default

    @classmethod
    def load_from_db(cls, db_session):
        """从数据库加载配置（兼容旧代码）"""
        try:
            from server_models import SystemConfig

            # 加载清理配置
            cleanup_config = (
                db_session.query(SystemConfig)
                .filter(SystemConfig.key == "cleanup")
                .first()
            )
            if cleanup_config:
                cls.AUTO_CLEANUP_ENABLED = cleanup_config.value.get(
                    "enabled", cls.AUTO_CLEANUP_ENABLED
                )
                cls.SCREENSHOT_RETENTION_HOURS = cleanup_config.value.get(
                    "retention_hours", cls.SCREENSHOT_RETENTION_HOURS
                )
                cls.CLEANUP_INTERVAL = int(
                    cleanup_config.value.get(
                        "interval_hours", cls.CLEANUP_INTERVAL / 3600
                    )
                    * 3600
                )

            # 加载截图配置
            screenshot_config = (
                db_session.query(SystemConfig)
                .filter(SystemConfig.key == "screenshot")
                .first()
            )
            if screenshot_config:
                cls.SCREENSHOT_INTERVAL = screenshot_config.value.get(
                    "interval", cls.SCREENSHOT_INTERVAL
                )
                cls.SCREENSHOT_QUALITY = screenshot_config.value.get(
                    "quality", cls.SCREENSHOT_QUALITY
                )
                cls.SCREENSHOT_FORMAT = screenshot_config.value.get(
                    "format", cls.SCREENSHOT_FORMAT
                )

        except Exception as e:
            logger.error(f"从数据库加载配置失败: {e}")


# ===== 为了方便直接使用，导出常用配置 =====
# 这些变量保持原样，让旧代码可以无缝迁移

# 基础配置
DEBUG = Config.DEBUG
SECRET_KEY = Config.SECRET_KEY

# 数据库配置
PRIMARY_DATABASE_URL = Config.PRIMARY_DATABASE_URL
BACKUP_DATABASE_URL = Config.BACKUP_DATABASE_URL
CA_CERT_PATH = Config.CA_CERT_PATH

# JWT配置
ALGORITHM = Config.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = Config.ACCESS_TOKEN_EXPIRE_MINUTES

# 管理员配置
ADMIN_USERNAME = Config.ADMIN_USERNAME
ADMIN_PASSWORD = Config.ADMIN_PASSWORD

# 存储配置
SCREENSHOT_DIR = Config.SCREENSHOT_DIR
SCREENSHOT_FORMAT = Config.SCREENSHOT_FORMAT
SCREENSHOT_QUALITY = Config.SCREENSHOT_QUALITY
SCREENSHOT_INTERVAL = Config.SCREENSHOT_INTERVAL

# 自动清理配置
# AUTO_CLEANUP_ENABLED = Config.AUTO_CLEANUP_ENABLED
# CLEANUP_INTERVAL = Config.CLEANUP_INTERVAL
# SCREENSHOT_RETENTION_HOURS = Config.SCREENSHOT_RETENTION_HOURS

# Redis配置
REDIS_URL = Config.REDIS_URL

# 性能配置
GUNICORN_WORKERS = Config.GUNICORN_WORKERS
LOG_LEVEL = Config.LOG_LEVEL

# 其他配置
THUMBNAIL_SIZE = Config.THUMBNAIL_SIZE
THUMBNAIL_QUALITY = Config.THUMBNAIL_QUALITY
MAX_UPLOAD_SIZE = Config.MAX_UPLOAD_SIZE
ALLOWED_EXTENSIONS = Config.ALLOWED_EXTENSIONS
MAX_WORKERS = Config.MAX_WORKERS
REQUEST_TIMEOUT = Config.REQUEST_TIMEOUT
DB_POOL_SIZE = Config.DB_POOL_SIZE
DB_MAX_OVERFLOW = Config.DB_MAX_OVERFLOW
DB_POOL_RECYCLE = Config.DB_POOL_RECYCLE
