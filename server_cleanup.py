# server_cleanup.py - 完整版

"""
数据清理模块 - 定时删除过期数据
"""
import logging
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.orm import Session

from server_database import PrimarySessionLocal
from server_config import Config
from server_timezone import get_beijing_now, get_utc_now, make_naive

logger = logging.getLogger(__name__)


class DataCleanup:
    """数据清理管理器 - 保持与上传接口一致的时间处理"""

    def __init__(self):
        """初始化清理管理器"""
        self.storage_path = Path(Config.SCREENSHOT_DIR)
        self.running = False
        self._retention_hours = Config.SCREENSHOT_RETENTION_HOURS
        self._enabled = Config.AUTO_CLEANUP_ENABLED
        self._interval = Config.CLEANUP_INTERVAL
        self._last_config_check = get_beijing_now()

    @property
    def retention_hours(self):
        return Config.SCREENSHOT_RETENTION_HOURS

    def _refresh_config(self):
        """刷新配置"""
        old_retention = self._retention_hours
        old_enabled = self._enabled
        old_interval = self._interval

        new_retention = Config.SCREENSHOT_RETENTION_HOURS
        new_enabled = Config.AUTO_CLEANUP_ENABLED
        new_interval = Config.CLEANUP_INTERVAL

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
        self._refresh_config()

        if not self._enabled:
            logger.info("自动清理未启用")
            return

        self.running = True
        logger.info(
            f"自动清理任务已启动，间隔: {self._interval/3600:.1f}小时，保留: {self._retention_hours}小时"
        )

        loop = asyncio.get_event_loop()

        # 启动时执行一次
        logger.info("执行启动时全面清理...")
        await loop.run_in_executor(None, self._cleanup_all_tables_sync)
        await loop.run_in_executor(None, self._cleanup_screenshots_sync)

        consecutive_errors = 0

        while self.running:
            try:
                self._refresh_config()

                if not self._enabled:
                    logger.info("自动清理已禁用，任务停止")
                    self.running = False
                    break

                await asyncio.sleep(self._interval)

                if self.running:
                    self._refresh_config()
                    await loop.run_in_executor(None, self._cleanup_all_tables_sync)
                    await loop.run_in_executor(None, self._cleanup_screenshots_sync)

                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                backoff_time = min(60 * consecutive_errors, 3600)
                logger.error(f"清理任务异常 (第{consecutive_errors}次): {e}")
                await asyncio.sleep(backoff_time)

    def _cleanup_all_tables_sync(self):
        """清理所有其他表"""
        logger.info("=" * 60)
        logger.debug("🧹 开始清理其他数据表")
        logger.info("=" * 60)

        db = PrimarySessionLocal()

        try:
            try:
                policies = db.execute(
                    text(
                        """
                        SELECT table_name, enabled, retention_days, retention_hours
                        FROM cleanup_policies
                        WHERE enabled = true
                        ORDER BY priority ASC
                    """
                    )
                ).fetchall()
            except Exception as e:
                logger.error(f"清理策略表不存在或查询失败: {e}")
                logger.info("请运行 SQL 创建 cleanup_policies 表")
                return

            results = {}

            for policy in policies:
                table_name = policy[0]

                try:
                    if table_name == "screenshots":
                        continue
                    elif table_name == "browser_history":
                        count = self._cleanup_browser_history_sync(db)
                    elif table_name == "activities":
                        count = self._cleanup_activities_sync(db)
                    elif table_name == "app_usage":
                        count = self._cleanup_app_usage_sync(db)
                    elif table_name == "file_operations":
                        count = self._cleanup_file_operations_sync(db)
                    elif table_name == "notifications":
                        count = self._cleanup_notifications_sync(db)
                    else:
                        continue

                    results[table_name] = count
                    logger.info(f"✅ {table_name}: 清理 {count} 条记录")

                    self._update_cleanup_time_sync(db, table_name, count)

                except Exception as e:
                    logger.error(f"❌ 清理 {table_name} 失败: {e}")
                    results[table_name] = -1

            self._cleanup_temp_files_sync()

            logger.info("=" * 60)
            logger.info(f"🎉 其他表清理完成: {results}")
            logger.info("=" * 60)

            return results

        except Exception as e:
            logger.error(f"全面清理失败: {e}")
            raise
        finally:
            db.close()

    def _cleanup_activities_sync(self, db: Session):
        """清理活动日志 - 统一使用UTC时间"""
        try:
            policy = db.execute(
                text(
                    "SELECT retention_days FROM cleanup_policies WHERE table_name = 'activities'"
                )
            ).first()
            retention_days = policy[0] if policy else 30

            # ✅ 统一使用 UTC 时间（与 browser_history 保持一致）
            cutoff = get_utc_now() - timedelta(days=retention_days)
            cutoff_naive = make_naive(cutoff)

            result = db.execute(
                text("DELETE FROM activities WHERE created_at < :cutoff RETURNING id"),
                {"cutoff": cutoff_naive},
            )
            deleted = result.rowcount
            db.commit()
            logger.info(f"清理活动日志: {deleted} 条 (保留{retention_days}天)")
            return deleted
        except Exception as e:
            logger.error(f"清理活动日志失败: {e}")
            return 0

    def _cleanup_browser_history_sync(self, db: Session):
        """清理浏览器历史 - UTC时间"""
        try:
            policy = db.execute(
                text(
                    "SELECT retention_days FROM cleanup_policies WHERE table_name = 'browser_history'"
                )
            ).first()
            retention_days = policy[0] if policy else 7
            cutoff = get_utc_now() - timedelta(days=retention_days)
            cutoff_naive = make_naive(cutoff)

            result = db.execute(
                text(
                    "DELETE FROM browser_history WHERE visit_time < :cutoff RETURNING id"
                ),
                {"cutoff": cutoff_naive},
            )
            deleted = result.rowcount
            db.commit()
            logger.info(f"清理浏览器历史: {deleted} 条 (保留{retention_days}天)")
            return deleted
        except Exception as e:
            logger.error(f"清理浏览器历史失败: {e}")
            return 0

    def _cleanup_app_usage_sync(self, db: Session):
        """清理软件使用记录 - UTC时间"""
        try:
            policy = db.execute(
                text(
                    "SELECT retention_days FROM cleanup_policies WHERE table_name = 'app_usage'"
                )
            ).first()
            retention_days = policy[0] if policy else 30
            cutoff = get_utc_now() - timedelta(days=retention_days)
            cutoff_naive = make_naive(cutoff)

            result = db.execute(
                text("DELETE FROM app_usage WHERE start_time < :cutoff RETURNING id"),
                {"cutoff": cutoff_naive},
            )
            deleted = result.rowcount
            db.commit()
            logger.info(f"清理软件使用记录: {deleted} 条 (保留{retention_days}天)")
            return deleted
        except Exception as e:
            logger.error(f"清理软件使用记录失败: {e}")
            return 0

    def _cleanup_file_operations_sync(self, db: Session):
        """清理文件操作记录 - UTC时间"""
        try:
            policy = db.execute(
                text(
                    "SELECT retention_days FROM cleanup_policies WHERE table_name = 'file_operations'"
                )
            ).first()
            retention_days = policy[0] if policy else 30
            cutoff = get_utc_now() - timedelta(days=retention_days)
            cutoff_naive = make_naive(cutoff)

            result = db.execute(
                text(
                    "DELETE FROM file_operations WHERE operation_time < :cutoff RETURNING id"
                ),
                {"cutoff": cutoff_naive},
            )
            deleted = result.rowcount
            db.commit()
            logger.info(f"清理文件操作记录: {deleted} 条 (保留{retention_days}天)")
            return deleted
        except Exception as e:
            logger.error(f"清理文件操作记录失败: {e}")
            return 0

    def _cleanup_notifications_sync(self, db: Session):
        """清理过期通知 - UTC时间"""
        try:
            policy = db.execute(
                text(
                    "SELECT retention_days FROM cleanup_policies WHERE table_name = 'notifications'"
                )
            ).first()
            retention_days = policy[0] if policy else 7
            cutoff = get_utc_now() - timedelta(days=retention_days)
            cutoff_naive = make_naive(cutoff)

            result = db.execute(
                text(
                    """
                    DELETE FROM notifications 
                    WHERE is_deleted = true AND updated_at < :cutoff 
                    RETURNING id
                """
                ),
                {"cutoff": cutoff_naive},
            )
            deleted = result.rowcount
            db.commit()
            logger.info(f"清理过期通知: {deleted} 条 (保留{retention_days}天)")
            return deleted
        except Exception as e:
            logger.error(f"清理过期通知失败: {e}")
            return 0

    def _cleanup_screenshots_sync(self):
        """清理截图 - 北京时间（与上传接口一致）"""
        current_retention = self.retention_hours
        if current_retention <= 0:
            logger.debug("保留时间设置为0，不执行清理")
            return

        try:
            beijing_now = get_beijing_now()
            beijing_cutoff = beijing_now - timedelta(hours=current_retention)
            cutoff_naive = beijing_cutoff.replace(tzinfo=None)

            logger.debug(f"🔍 开始清理 {current_retention} 小时前的数据")
            logger.debug(
                f"    截止时间(北京时间): {beijing_cutoff.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            db = PrimarySessionLocal()

            try:
                batch_size = 500
                last_id = 0
                batch_count = 0
                total_deleted_records = 0
                total_deleted_files = 0
                total_deleted_thumbnails = 0
                all_failed_records = []

                # 统计
                count_result = db.execute(
                    text(
                        """
                        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
                        FROM screenshots
                        WHERE screenshot_time < :cutoff
                    """
                    ),
                    {"cutoff": cutoff_naive},
                ).first()

                if count_result and count_result[0] > 0:
                    logger.debug(
                        f"📊 待清理统计: {count_result[0]} 条记录, "
                        f"{count_result[1]/1024/1024:.2f} MB"
                    )
                else:
                    logger.debug("📭 没有需要清理的数据")
                    return

                while True:
                    batch = db.execute(
                        text(
                            """
                            SELECT id, filename, thumbnail
                            FROM screenshots
                            WHERE screenshot_time < :cutoff
                            AND id > :last_id
                            ORDER BY id
                            LIMIT :limit
                        """
                        ),
                        {
                            "cutoff": cutoff_naive,
                            "last_id": last_id,
                            "limit": batch_size,
                        },
                    ).fetchall()

                    if not batch:
                        break

                    batch_count += 1
                    logger.debug(f"📦 处理第 {batch_count} 批次: {len(batch)} 条")

                    success_ids = []
                    batch_failed = []

                    for row in batch:
                        ss_id, filename, thumbnail = row
                        file_ok = True

                        if filename:
                            file_path = self.storage_path / filename
                            if file_path.exists():
                                try:
                                    file_path.unlink()
                                    total_deleted_files += 1
                                except Exception as e:
                                    file_ok = False
                                    batch_failed.append(
                                        {"id": ss_id, "file": filename, "error": str(e)}
                                    )

                        if thumbnail:
                            try:
                                thumb_path = self.storage_path / thumbnail
                                if thumb_path.exists():
                                    thumb_path.unlink()
                                    total_deleted_thumbnails += 1
                            except Exception as e:
                                logger.warning(f"⚠️ 删除缩略图失败 {thumbnail}: {e}")

                        if file_ok:
                            success_ids.append(ss_id)

                    if success_ids:
                        result = db.execute(
                            text(
                                "DELETE FROM screenshots WHERE id = ANY(:ids) RETURNING id"
                            ),
                            {"ids": success_ids},
                        )
                        total_deleted_records += len(result.fetchall())

                        if batch_count % 10 == 0:
                            db.commit()
                            logger.debug(f"💾 已提交 {batch_count} 个批次")

                    all_failed_records.extend(batch_failed)
                    last_id = batch[-1][0]

                db.commit()

                if total_deleted_records > 0:
                    details = {
                        "deleted_records": total_deleted_records,
                        "deleted_files": total_deleted_files,
                        "deleted_thumbnails": total_deleted_thumbnails,
                        "failed_count": len(all_failed_records),
                        "retention_hours": current_retention,
                        "cutoff_time": beijing_cutoff.isoformat(),
                        "batches_processed": batch_count,
                    }

                    if all_failed_records:
                        details["failed_samples"] = all_failed_records[:10]

                    db.execute(
                        text(
                            """
                            INSERT INTO activities (employee_id, action, details, created_at)
                            VALUES ('system', 'auto_cleanup', :details, :now)
                        """
                        ),
                        {
                            "details": json.dumps(details, ensure_ascii=False),
                            "now": beijing_now,
                        },
                    )
                    db.commit()

                    logger.debug(
                        f"🎉 清理完成: {total_deleted_records} 条记录, "
                        f"{total_deleted_files} 个文件, "
                        f"{total_deleted_thumbnails} 个缩略图"
                    )

            except Exception as e:
                logger.error(f"❌ 清理过程中出错: {e}", exc_info=True)
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ 清理失败: {e}", exc_info=True)

    def _cleanup_temp_files_sync(self):
        """清理临时文件"""
        temp_dir = self.storage_path / "temp"
        if not temp_dir.exists():
            return

        try:
            cutoff = get_utc_now() - timedelta(hours=24)
            cutoff_naive = make_naive(cutoff)

            deleted = 0
            for file_path in temp_dir.rglob("*"):
                if file_path.is_file():
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_naive:
                        file_path.unlink()
                        deleted += 1

            if deleted > 0:
                logger.info(f"清理临时文件: {deleted} 个")
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")

    def _update_cleanup_time_sync(self, db: Session, table_name: str, count: int):
        """更新清理时间 - 统一使用 UTC 存储"""
        try:
            db.execute(
                text(
                    """
                    UPDATE cleanup_policies 
                    SET last_cleaned_at = :now, cleaned_count = :count
                    WHERE table_name = :table_name
                """
                ),
                {"now": get_utc_now(), "count": count, "table_name": table_name},
            )
            db.commit()
        except Exception as e:
            logger.debug(f"更新清理时间失败: {e}")

    def cleanup_old_data_once(self):
        """执行一次截图清理"""
        self._refresh_config()
        self._cleanup_screenshots_sync()

    def stop(self):
        """停止清理任务"""
        self.running = False
        logger.info("清理任务已停止")
