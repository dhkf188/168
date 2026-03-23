"""
员工监控系统 - 工具模块
保留向后兼容的导入
"""

# 从核心模块导入所有功能
from client_core import (
    setup_logging,
    retry,
    smart_retry,
    SystemInfoCollector,
    ConfigManager,
    AtomicFileOperation,
    BufferPool,
    get_buffer,
    put_buffer,
    HealthStatus,
    HealthRecord,
    ComponentHealth,
    HealthMonitor,
    HealthHistory,
    ProcessWatchdog,
    PerceptualHash,
    MultiMonitorScreenshot,
    APIClient,
    UploadQueue,
    UploadTask,
)

# 为了向后兼容
TrayIcon = None
AutoConfig = None

try:
    from client_tray import EnhancedTrayIcon as TrayIcon
except ImportError:
    pass

try:
    from client_i18n import I18nManager as AutoConfig
except ImportError:
    pass

__all__ = [
    'setup_logging',
    'retry',
    'smart_retry',
    'SystemInfoCollector',
    'ConfigManager',
    'AtomicFileOperation',
    'BufferPool',
    'get_buffer',
    'put_buffer',
    'HealthStatus',
    'HealthRecord',
    'ComponentHealth',
    'HealthMonitor',
    'HealthHistory',
    'ProcessWatchdog',
    'PerceptualHash',
    'MultiMonitorScreenshot',
    'APIClient',
    'UploadQueue',
    'UploadTask',
    'TrayIcon',
    'AutoConfig',
]