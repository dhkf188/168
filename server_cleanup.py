"""
数据清理模块 - 定时删除过期数据
"""

# 在 server_cleanup.py 文件顶部确保有这些导入
import asyncio
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import text
from sqlalchemy import func  # 添加这个导入

from server_database import PrimarySessionLocal
from server_config import Config
from server_timezone import (
    get_beijing_now,
    get_utc_now,
    to_beijing_time,
    to_utc_time,
    make_naive,
    make_aware,
    UTC,
)

logger = logging.getLogger(__name__)


class DataCleanup:
    """数据清理管理器"""

    def __init__(self):
        """初始化清理管理器"""
        self.storage_path = Path(Config.SCREENSHOT_DIR)
        self.running = False
        # 统一使用内部缓存变量
        self._retention_hours = Config.SCREENSHOT_RETENTION_HOURS
        self._enabled = Config.AUTO_CLEANUP_ENABLED
        self._interval = Config.CLEANUP_INTERVAL
        # 记录上次配置检查时间
        self._last_config_check = get_beijing_now()

    @property
    def retention_hours(self):
        """保留时间属性 - 每次使用都从Config获取最新值"""
        return Config.SCREENSHOT_RETENTION_HOURS

    def _refresh_config(self):
        """刷新配置（从Config类获取最新值）"""
        old_retention = self._retention_hours
        old_enabled = self._enabled
        old_interval = self._interval

        # 从Config类获取最新配置
        new_retention = Config.SCREENSHOT_RETENTION_HOURS
        new_enabled = Config.AUTO_CLEANUP_ENABLED
        new_interval = Config.CLEANUP_INTERVAL

        # 记录配置变化（仅在变化时记录）
        changes = []
        if old_retention != new_retention:
            changes.append(f"保留时间: {old_retention}小时 -> {new_retention}小时")
            self._retention_hours = new_retention

        if old_enabled != new_enabled:
            changes.append(f"清理开关: {old_enabled} -> {new_enabled}")
            self._enabled = new_enabled

        if old_interval != new_interval:
            changes.append(
                f"清理间隔: {old_interval/3600:.1f}小时 -> {new_interval/3600:.1f}小时"
            )
            self._interval = new_interval

        if changes:
            logger.info(f"🔄 配置已更新: {'; '.join(changes)}")

    async def start_cleanup_task(self):
        """启动清理任务"""
        # 启动前刷新配置
        self._refresh_config()

        if not self._enabled:
            logger.info("自动清理未启用")
            return

        self.running = True
        logger.info(
            f"自动清理任务已启动，间隔: {self._interval/3600:.1f}小时，保留: {self._retention_hours}小时"
        )

        consecutive_errors = 0

        while self.running:
            try:
                # 每次循环都刷新配置（确保配置变化能及时生效）
                self._refresh_config()

                # 如果清理被禁用，停止任务
                if not self._enabled:
                    logger.info("自动清理已禁用，任务停止")
                    self.running = False
                    break

                # 等待指定的间隔时间
                await asyncio.sleep(self._interval)

                if self.running:
                    # 执行清理前再次刷新配置
                    self._refresh_config()
                    await self.cleanup_old_data()

                consecutive_errors = 0  # 成功执行后重置错误计数

            except Exception as e:
                consecutive_errors += 1
                backoff_time = min(60 * consecutive_errors, 3600)  # 指数退避，最多1小时
                logger.error(f"清理任务异常 (第{consecutive_errors}次): {e}")
                await asyncio.sleep(backoff_time)

    async def cleanup_old_data_once(self):
        """执行一次清理"""
        # 执行前刷新配置
        self._refresh_config()
        await self.cleanup_old_data()

    async def cleanup_old_data(self):
        """清理旧数据 - 修复时区问题"""
        # 使用最新的保留时间
        current_retention = self.retention_hours

        if current_retention <= 0:
            logger.info("保留时间设置为0，不执行清理")
            return

        try:
            from server_timezone import get_beijing_now, to_utc_time, make_naive
            import json
            from pathlib import Path

            # ===== 1. 计算截止时间 =====
            beijing_now = get_beijing_now()
            beijing_cutoff = beijing_now - timedelta(hours=current_retention)

            # 🚨 关键修复：将北京时间截止时间转换为 UTC 用于数据库查询
            utc_cutoff = to_utc_time(beijing_cutoff)  # 转换为 UTC aware
            utc_cutoff_naive = make_naive(utc_cutoff)  # 转换为 naive UTC

            logger.info(f"🔍 开始清理 {current_retention} 小时前的数据...")
            logger.info(f"📅 当前北京时间: {beijing_now.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(
                f"⏰ 北京时间截止: {beijing_cutoff.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            logger.info(f"🕒 UTC截止(naive): {utc_cutoff_naive}")

            # 使用数据库会话
            db = PrimarySessionLocal()

            try:
                # ===== 2. 先统计待清理数据（使用 UTC 时间）=====
                stats_result = db.execute(
                    text(
                        """
                        SELECT 
                            COUNT(*) as record_count, 
                            COALESCE(SUM(file_size), 0) as total_size,
                            COUNT(CASE WHEN thumbnail IS NOT NULL THEN 1 END) as thumb_count
                        FROM screenshots 
                        WHERE screenshot_time < :cutoff
                    """
                    ),
                    {"cutoff": utc_cutoff_naive},  # ✅ 使用 UTC 时间
                ).first()

                if stats_result:
                    pending_count = stats_result[0] or 0
                    pending_size = stats_result[1] or 0
                    thumb_count = stats_result[2] or 0

                    if pending_count == 0:
                        logger.info("没有需要清理的数据")
                        return

                    logger.info(f"📊 待清理统计:")
                    logger.info(f"   - 记录数: {pending_count} 条")
                    logger.info(f"   - 总大小: {pending_size/1024/1024:.2f} MB")
                    logger.info(f"   - 缩略图: {thumb_count} 个")

                # ===== 3. 分批获取要删除的记录 =====
                batch_size = 100
                offset = 0
                total_deleted = 0
                total_files = 0
                total_size_freed = 0
                failed_files = []

                while True:
                    # 分批获取（使用 UTC 时间）
                    screenshots_batch = db.execute(
                        text(
                            """
                            SELECT id, filename, thumbnail 
                            FROM screenshots 
                            WHERE screenshot_time < :cutoff
                            ORDER BY id
                            LIMIT :limit OFFSET :offset
                        """
                        ),
                        {
                            "cutoff": utc_cutoff_naive,  # ✅ 使用 UTC 时间
                            "limit": batch_size,
                            "offset": offset,
                        },
                    ).fetchall()

                    if not screenshots_batch:
                        break

                    logger.debug(
                        f"处理批次: {offset} - {offset + len(screenshots_batch)}"
                    )

                    # ===== 4. 删除文件 =====
                    for screenshot in screenshots_batch:
                        screenshot_id, filename, thumbnail = screenshot

                        # 删除原图
                        if filename:
                            try:
                                file_path = self.storage_path / filename
                                if file_path.exists():
                                    file_size = file_path.stat().st_size
                                    file_path.unlink()
                                    total_size_freed += file_size
                                    total_files += 1
                                    logger.debug(
                                        f"✅ 已删除文件: {filename} ({file_size} bytes)"
                                    )
                                else:
                                    logger.warning(f"⚠️ 文件不存在: {filename}")
                            except Exception as e:
                                failed_files.append({"file": filename, "error": str(e)})
                                logger.error(f"❌ 删除文件失败 {filename}: {e}")

                        # 删除缩略图
                        if thumbnail:
                            try:
                                thumb_path = self.storage_path / thumbnail
                                if thumb_path.exists():
                                    thumb_path.unlink()
                                    logger.debug(f"✅ 已删除缩略图: {thumbnail}")
                            except Exception as e:
                                logger.error(f"❌ 删除缩略图失败 {thumbnail}: {e}")

                    offset += len(screenshots_batch)

                # ===== 5. 删除数据库记录（使用 UTC 时间）=====
                result = db.execute(
                    text(
                        """
                        DELETE FROM screenshots 
                        WHERE screenshot_time < :cutoff
                        RETURNING id
                    """
                    ),
                    {"cutoff": utc_cutoff_naive},  # ✅ 使用 UTC 时间
                )

                deleted_records = result.fetchall()
                total_deleted = len(deleted_records)

                # 提交事务
                db.commit()

                # ===== 6. 记录结果 =====
                if total_deleted > 0:
                    success_message = (
                        f"✅ 清理完成:\n"
                        f"   - 删除记录: {total_deleted} 条\n"
                        f"   - 删除文件: {total_files} 个\n"
                        f"   - 释放空间: {total_size_freed/1024/1024:.2f} MB"
                    )

                    if failed_files:
                        success_message += f"\n   - 失败文件: {len(failed_files)} 个"

                    logger.info(success_message)

                    # 记录清理活动（使用北京时间记录）
                    try:
                        db.execute(
                            text(
                                """
                                INSERT INTO activities (employee_id, action, details, created_at)
                                VALUES ('system', 'auto_cleanup', :details, :now)
                            """
                            ),
                            {
                                "details": json.dumps(
                                    {
                                        "deleted_records": total_deleted,
                                        "deleted_files": total_files,
                                        "size_freed_bytes": total_size_freed,
                                        "size_freed_mb": round(
                                            total_size_freed / (1024 * 1024), 2
                                        ),
                                        "retention_hours": current_retention,
                                        "cutoff_time": beijing_cutoff.isoformat(),  # 记录北京时间
                                        "failed_files": failed_files[:10],
                                        "failed_count": len(failed_files),
                                    },
                                    ensure_ascii=False,
                                ),
                                "now": beijing_now,  # 使用北京时间记录
                            },
                        )
                        db.commit()
                        logger.info("📝 清理活动已记录")
                    except Exception as e:
                        logger.error(f"记录清理活动失败: {e}")
                else:
                    logger.info("没有需要清理的数据")

            except Exception as e:
                logger.error(f"❌ 清理过程中出错: {e}", exc_info=True)
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ 清理失败: {e}", exc_info=True)

    def stop(self):
        """停止清理任务"""
        self.running = False
        logger.info("清理任务已停止")


# ==================== 🚨 遗漏的 API 接口 ====================
# 这个函数需要在 server_main.py 中调用，但需要在 server_cleanup.py 中定义
def get_cleanup_status(db):
    """
    获取清理状态 - 修复时区问题
    这个函数被 server_main.py 中的 /api/cleanup/status 调用
    """
    try:
        from server_timezone import get_beijing_now, to_utc_time, make_naive

        # ===== 1. 获取北京时间 =====
        beijing_now = get_beijing_now()
        retention_hours = Config.SCREENSHOT_RETENTION_HOURS

        # ===== 2. 计算截止时间（北京时间）并转换为 UTC =====
        beijing_cutoff = beijing_now - timedelta(hours=retention_hours)
        utc_cutoff = to_utc_time(beijing_cutoff)  # 转换为 UTC aware
        utc_cutoff_naive = make_naive(utc_cutoff)  # 转换为 naive UTC

        logger.debug(f"清理状态计算 - 北京时间: {beijing_now}")
        logger.debug(f"北京时间截止: {beijing_cutoff}")
        logger.debug(f"UTC截止(naive): {utc_cutoff_naive}")

        # ===== 3. 查询待清理截图（使用 UTC 时间）=====
        pending_stats = db.execute(
            text(
                """
                SELECT 
                    COUNT(*) as record_count, 
                    COALESCE(SUM(file_size), 0) as total_size
                FROM screenshots 
                WHERE screenshot_time < :cutoff
            """
            ),
            {"cutoff": utc_cutoff_naive},  # ✅ 使用 UTC 时间
        ).first()

        pending_count = pending_stats[0] if pending_stats else 0
        pending_size = pending_stats[1] if pending_stats else 0

        # ===== 4. 获取总截图数量和大小 =====
        total_stats = db.execute(
            text(
                """
                SELECT 
                    COUNT(*) as total_count, 
                    COALESCE(SUM(file_size), 0) as total_size
                FROM screenshots
            """
            )
        ).first()

        total_count = total_stats[0] if total_stats else 0
        total_size = total_stats[1] if total_stats else 0

        # ===== 5. 获取上次清理时间 =====
        last_cleanup_result = db.execute(
            text(
                """
                SELECT created_at
                FROM activities 
                WHERE action = 'auto_cleanup'
                ORDER BY created_at DESC
                LIMIT 1
            """
            )
        ).first()

        last_cleanup_time = None
        if last_cleanup_result and last_cleanup_result[0]:
            # 数据库存储的是 UTC naive，转换为北京时间显示
            from server_timezone import to_beijing_time, make_aware

            utc_naive = last_cleanup_result[0]
            utc_aware = make_aware(utc_naive, UTC)  # 先转换为 UTC aware
            last_cleanup_time = to_beijing_time(utc_aware)  # 再转换为北京时间

        # ===== 6. 计算下次清理时间 =====
        next_cleanup_time = None
        if Config.AUTO_CLEANUP_ENABLED and last_cleanup_time:
            interval_seconds = Config.CLEANUP_INTERVAL
            next_cleanup_time = last_cleanup_time + timedelta(seconds=interval_seconds)

        # ===== 7. 计算清理百分比 =====
        pending_percent = 0
        if total_size > 0:
            pending_percent = round((pending_size / total_size) * 100, 2)

        # ===== 8. 返回结果 =====
        return {
            # 配置信息
            "enabled": Config.AUTO_CLEANUP_ENABLED,
            "retention_hours": retention_hours,
            "interval_hours": round(Config.CLEANUP_INTERVAL / 3600, 1),
            "cleanup_time": getattr(Config, "CLEANUP_TIME", None),
            # 待清理信息
            "pending_cleanup": pending_count,
            "pending_size_mb": round(pending_size / (1024 * 1024), 2),
            "pending_percent": pending_percent,
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
        return {
            "enabled": Config.AUTO_CLEANUP_ENABLED,
            "retention_hours": Config.SCREENSHOT_RETENTION_HOURS,
            "interval_hours": Config.CLEANUP_INTERVAL / 3600,
            "pending_cleanup": 0,
            "pending_size_mb": 0,
            "total_screenshots": 0,
            "total_size_mb": 0,
            "last_cleanup": None,
            "error": str(e) if Config.DEBUG else None,
        }
