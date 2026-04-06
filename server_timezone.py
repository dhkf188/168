# server_timezone.py - 完整修复版

"""
时区处理工具 - 统一管理北京时间转换
所有时间都以北京时间（UTC+8）存储和显示
使用 aware datetime 避免弃用警告
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)

# 北京时间偏移量（小时）
BEIJING_OFFSET = 8
# UTC时区
UTC = timezone.utc
# 北京时间时区
BEIJING_TZ = timezone(timedelta(hours=BEIJING_OFFSET))


def get_utc_now() -> datetime:
    """
    获取当前UTC时间（aware）

    Returns:
        datetime: 当前UTC时间（有时区信息）
    """
    return datetime.now(UTC)


def get_beijing_now() -> datetime:
    """
    获取当前北京时间（aware）

    Returns:
        datetime: 当前北京时间（有时区信息）
    """
    return datetime.now(BEIJING_TZ)


def to_beijing_time(dt: Optional[datetime]) -> Optional[datetime]:
    """
    将任意时间转换为北京时间（aware）

    Args:
        dt: 输入的时间（可以是naive或aware）

    Returns:
        转换后的北京时间（aware），如果输入为None则返回None
    """
    if dt is None:
        return None

    # 如果时间是naive，假设它是UTC时间
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    # 转换为北京时间
    return dt.astimezone(BEIJING_TZ)


def to_utc_time(dt: Optional[datetime]) -> Optional[datetime]:
    """
    将任意时间转换为UTC时间（aware）

    Args:
        dt: 输入的时间（可以是naive或aware）

    Returns:
        转换后的UTC时间（aware），如果输入为None则返回None
    """
    if dt is None:
        return None

    # 如果时间是naive，假设它是北京时间
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)

    # 转换为UTC时间
    return dt.astimezone(UTC)


def make_naive(dt: datetime) -> datetime:
    """
    将aware datetime转换为naive datetime（用于数据库存储）
    数据库通常存储为无时区信息的时间，我们统一存储为UTC时间

    Args:
        dt: aware datetime

    Returns:
        naive datetime (UTC)
    """
    if dt.tzinfo is None:
        return dt
    # 转换为UTC并移除时区信息
    return dt.astimezone(UTC).replace(tzinfo=None)


def make_aware(dt: datetime, target_tz: timezone = BEIJING_TZ) -> datetime:
    """
    将naive datetime转换为aware datetime

    Args:
        dt: naive datetime
        target_tz: 目标时区

    Returns:
        aware datetime
    """
    if dt.tzinfo is not None:
        return dt.astimezone(target_tz)
    return dt.replace(tzinfo=target_tz)


def format_beijing_time(
    dt: Optional[datetime], format_str: str = "%Y-%m-%d %H:%M:%S"
) -> Optional[str]:
    """
    格式化北京时间为字符串

    Args:
        dt: 要格式化的时间
        format_str: 格式化字符串

    Returns:
        格式化后的时间字符串
    """
    if dt is None:
        return None
    beijing_time = to_beijing_time(dt)
    return beijing_time.strftime(format_str)


def get_date_range_for_day(target_date: Optional[datetime] = None):
    """
    获取指定日期的开始和结束时间（北京时间）

    Args:
        target_date: 目标日期，如果为None则使用今天

    Returns:
        tuple: (开始时间, 结束时间) - 返回aware datetime
    """
    if target_date is None:
        target_date = get_beijing_now()
    else:
        target_date = to_beijing_time(target_date)

    # 获取当天的开始时间
    start_time = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    # 获取当天的结束时间（第二天的开始）
    end_time = start_time + timedelta(days=1)

    return start_time, end_time


def parse_beijing_datetime(datetime_str: str) -> Optional[datetime]:
    """
    解析北京时间字符串

    Args:
        datetime_str: 时间字符串，格式如 "2026-03-12 13:30:00"

    Returns:
        aware datetime对象（北京时间）
    """
    try:
        # 尝试解析完整格式
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            # 尝试解析没有秒的格式
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                # 尝试解析只有日期的格式
                dt = datetime.strptime(datetime_str, "%Y-%m-%d")
            except ValueError:
                logger.error(f"无法解析时间字符串: {datetime_str}")
                return None

    # 添加北京时间时区
    return dt.replace(tzinfo=BEIJING_TZ)


def validate_beijing_time(dt: datetime) -> bool:
    """
    验证时间是否为有效的北京时间

    Args:
        dt: 要验证的时间

    Returns:
        bool: 是否有效
    """
    if dt is None:
        return False

    # 检查年份范围
    if dt.year < 2000 or dt.year > 2100:
        return False

    return True


def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """序列化datetime为ISO格式字符串（输出北京时间）"""
    if dt is None:
        return None
    beijing_time = to_beijing_time(dt)
    return beijing_time.strftime("%Y-%m-%d %H:%M:%S")


# 为了方便，直接导出常用函数
__all__ = [
    "UTC",
    "BEIJING_TZ",
    "get_utc_now",
    "get_beijing_now",
    "to_beijing_time",
    "to_utc_time",
    "make_naive",
    "make_aware",
    "format_beijing_time",
    "get_date_range_for_day",
    "parse_beijing_datetime",
    "validate_beijing_time",
]
