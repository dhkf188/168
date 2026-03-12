"""
客户端配置文件 - 仅供首次注册使用，注册后由服务器完全控制
"""

import os
from pathlib import Path


class Config:
    # ========== 服务器配置（必须配置）==========
    # 默认服务器地址列表（按优先级排序）
    # 注意：客户端连接后，所有配置将由服务器下发，本地配置将被覆盖
    DEFAULT_SERVERS = [
        "http://localhost:8000",  # 本地服务器优先
        "https://your-server.onrender.com",  # 远程服务器作为备用
    ]

    # ========== 首次注册时的默认配置 ==========
    # 这些配置仅在客户端首次注册时使用
    # 注册成功后，所有配置将由服务器动态下发，本地修改无效

    # 截图间隔（秒）- 仅首次注册时使用
    SCREENSHOT_INTERVAL = 60

    # 图片质量 - 仅首次注册时使用
    SCREENSHOT_QUALITY = 80

    # 图片格式 - 仅首次注册时使用
    SCREENSHOT_FORMAT = "webp"

    # ========== 本地文件配置 ==========
    # 这些配置不会被服务器覆盖，仅用于本地文件管理

    # 临时目录（存储日志、缓存等）
    TEMP_DIR = Path(os.path.expanduser("~")) / ".employee-monitor"

    # 日志配置
    LOG_FILE = TEMP_DIR / "client.log"
    LOG_LEVEL = "INFO"

    # ========== 客户端行为配置 ==========
    # 这些配置不会被服务器覆盖，控制客户端基本行为

    # 本地历史记录数量（用于相似度检测）
    MAX_HISTORY = 10

    # 图片相似度阈值（0-1）
    SIMILARITY_THRESHOLD = 0.95

    # 网络请求重试次数
    RETRY_TIMES = 3

    # 重试延迟（秒）
    RETRY_DELAY = 1

    # 心跳间隔（秒）- 客户端主动上报状态
    HEARTBEAT_INTERVAL = 60

    # 批量上传间隔（秒）- 用于离线缓存的上传
    BATCH_UPLOAD_INTERVAL = 3600
