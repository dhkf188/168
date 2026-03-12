# server_config_manager.py
"""
配置管理器 - 统一管理所有系统配置
优先级: 数据库配置 > 环境变量 > 默认值
"""

import logging
from typing import Any, Dict, Optional
from server_database import PrimarySessionLocal
from server_models import SystemConfig
from server_timezone import get_utc_now

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器 - 单例模式"""

    _instance = None
    _config_cache = {}
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.load_all_from_db()

    def load_all_from_db(self):
        """从数据库加载所有配置"""
        try:
            db = PrimarySessionLocal()
            configs = db.query(SystemConfig).all()

            self._config_cache.clear()
            for config in configs:
                self._config_cache[config.key] = config.value

            db.close()
            logger.info(f"✅ 从数据库加载 {len(configs)} 个配置项")
        except Exception as e:
            logger.error(f"从数据库加载配置失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config_cache.get(key, default)

    def set(
        self,
        key: str,
        value: Any,
        category: str = None,
        description: str = None,
        user_id: int = None,
    ) -> bool:
        """设置配置值（保存到数据库）"""
        try:
            db = PrimarySessionLocal()

            # 查找现有配置
            config = db.query(SystemConfig).filter(SystemConfig.key == key).first()

            from datetime import datetime

            now = get_utc_now()

            if config:
                # 更新现有配置
                config.value = value
                config.updated_at = now
                config.updated_by = user_id
                if category:
                    config.category = category
                if description:
                    config.description = description
            else:
                # 创建新配置
                config = SystemConfig(
                    key=key,
                    value=value,
                    category=category or "general",
                    description=description or "",
                    updated_at=now,
                    updated_by=user_id,
                )
                db.add(config)

            db.commit()

            # 更新缓存
            self._config_cache[key] = value

            logger.info(f"✅ 配置已保存: {key} = {value}")
            return True

        except Exception as e:
            logger.error(f"保存配置失败: {key} - {e}")
            return False
        finally:
            db.close()

    def get_all(self, category: Optional[str] = None) -> Dict[str, Any]:
        """获取所有配置"""
        if category:
            return {
                k: v
                for k, v in self._config_cache.items()
                if self._get_category(k) == category
            }
        return self._config_cache.copy()

    def _get_category(self, key: str) -> str:
        """根据key获取分类"""
        categories = {
            "screenshot_interval": "general",
            "screenshot_format": "general",
            "screenshot_quality": "general",
            "timezone": "general",
            "system_name": "general",
            "auto_cleanup_enabled": "cleanup",
            "screenshot_retention_hours": "cleanup",
            "cleanup_interval": "cleanup",
            "screenshot_dir": "storage",
            "max_storage_gb": "storage",
            "thumbnail_size": "storage",
            "thumbnail_quality": "storage",
            "jwt_expire_minutes": "security",
        }
        return categories.get(key, "other")


# 创建全局配置管理器实例
config_manager = ConfigManager()


# 便捷函数
def get_config(key: str, default: Any = None) -> Any:
    """获取配置"""
    return config_manager.get(key, default)


def set_config(
    key: str,
    value: Any,
    category: str = None,
    description: str = None,
    user_id: int = None,
) -> bool:
    """设置配置"""
    return config_manager.set(key, value, category, description, user_id)
