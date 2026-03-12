"""
数据库连接配置 - 支持主备切换，支持 Aiven SSL
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import logging

from server_config import Config

logger = logging.getLogger(__name__)


# ========== 关键修复：强制转换URL格式 ==========
def fix_database_url(url):
    """强制将 postgres:// 转换为 postgresql://"""
    if not url:
        return url

    # 打印原始URL（隐藏密码）
    safe_url = url
    if "@" in url:
        parts = url.split("@")
        auth_part = parts[0].split(":")
        if len(auth_part) > 2:
            safe_url = f"{auth_part[0]}:****@{parts[1]}"
    logger.info(f"原始URL: {safe_url}")

    # 强制转换
    if url.startswith("postgres://"):
        fixed_url = url.replace("postgres://", "postgresql://", 1)
        logger.info(f"✅ 数据库URL已修复: postgres:// -> postgresql://")
        return fixed_url

    return url


# ========== SSL 连接配置 ==========
# server_database.py


def get_connect_args():
    """获取数据库连接参数，支持 Aiven SSL"""
    connect_args = {}

    # 获取数据库URL（使用修复后的）
    db_url = Config.PRIMARY_DATABASE_URL or ""

    # 检查是否需要 SSL
    if "sslmode=require" in db_url or "aiven" in db_url.lower():
        connect_args["sslmode"] = "require"
        logger.info("✅ 启用 SSL 连接")

        # ===== 修改点：显式下载并指定 Aiven CA 证书 =====
        ca_cert_path = Config.CA_CERT_PATH

        # 如果证书不存在，尝试下载
        if not os.path.exists(ca_cert_path):
            try:
                import urllib.request

                logger.info(f"📥 下载 Aiven CA 证书到: {ca_cert_path}")
                urllib.request.urlretrieve(
                    "https://certs.aiven.io/ca.pem", ca_cert_path
                )
                logger.info("✅ CA 证书下载成功")
            except Exception as e:
                logger.error(f"❌ 下载 CA 证书失败: {e}")
                # 降级模式：不验证证书（仅用于测试）
                connect_args["sslmode"] = "require"
                connect_args["sslrootcert"] = None
                return connect_args

        # 使用下载的证书
        if os.path.exists(ca_cert_path):
            connect_args["sslrootcert"] = ca_cert_path
            logger.info(f"✅ 使用 CA 证书: {ca_cert_path}")
        else:
            logger.warning("⚠️ CA 证书不存在，使用系统证书")
            # 尝试使用系统证书
            if os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
                connect_args["sslrootcert"] = "/etc/ssl/certs/ca-certificates.crt"

    return connect_args


# ========== 修复主数据库URL ==========
fixed_primary_url = fix_database_url(Config.PRIMARY_DATABASE_URL)
logger.info(
    f"连接到主数据库: {fixed_primary_url.split('@')[-1] if '@' in fixed_primary_url else fixed_primary_url}"
)

# 主数据库引擎
primary_engine = create_engine(
    fixed_primary_url,  # 使用修复后的URL
    pool_size=Config.DB_POOL_SIZE,
    max_overflow=Config.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=Config.DB_POOL_RECYCLE,
    connect_args=get_connect_args(),
    echo=Config.DEBUG,
)

# 主数据库会话
PrimarySessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=primary_engine
)

# ========== 备用数据库（如果配置了）==========
backup_engine = None
BackupSessionLocal = None

if Config.BACKUP_DATABASE_URL:
    fixed_backup_url = fix_database_url(Config.BACKUP_DATABASE_URL)
    logger.info(
        f"连接到备用数据库: {fixed_backup_url.split('@')[-1] if '@' in fixed_backup_url else fixed_backup_url}"
    )

    backup_engine = create_engine(
        fixed_backup_url,
        pool_size=Config.DB_POOL_SIZE,
        max_overflow=Config.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=Config.DB_POOL_RECYCLE,
        connect_args=get_connect_args(),
        echo=Config.DEBUG,
    )
    BackupSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=backup_engine
    )

Base = declarative_base()

# 导出 engine 变量
engine = primary_engine

# 定义 __all__ 列表
__all__ = [
    "Base",
    "engine",
    "PrimarySessionLocal",
    "get_db",
    "get_backup_db",
    "get_db_context",
    "check_database_health",
]


def get_db():
    """获取主数据库会话"""
    db = PrimarySessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_backup_db():
    """获取备用数据库会话"""
    if not BackupSessionLocal:
        raise Exception("备用数据库未配置")
    db = BackupSessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """上下文管理器方式获取数据库会话"""
    db = PrimarySessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_health():
    """检查数据库健康状态"""
    try:
        db = PrimarySessionLocal()
        db.execute("SELECT 1")
        db.close()
        return True, "healthy"
    except Exception as e:
        logger.error(f"主数据库健康检查失败: {e}")

        # 尝试备用数据库
        if BackupSessionLocal:
            try:
                db = BackupSessionLocal()
                db.execute("SELECT 1")
                db.close()
                return True, "healthy (using backup)"
            except Exception as e2:
                logger.error(f"备用数据库健康检查失败: {e2}")
                return False, str(e2)

        return False, str(e)
