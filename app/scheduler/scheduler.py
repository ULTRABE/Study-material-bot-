"""
Scheduler: background tasks for TTL cleanup, expiry checks, disk monitoring.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.utils.helpers import get_disk_free_gb, ensure_dir

logger = logging.getLogger(__name__)

_scheduler: Optional["Scheduler"] = None


def get_scheduler() -> "Scheduler":
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


class Scheduler:
    """
    Background task scheduler.
    Runs periodic maintenance tasks.
    """

    def __init__(self):
        self._running = False
        self._tasks: list = []
        self._redis_service = None
        self._db_service_factory = None

    def configure(self, redis_service, db_session_factory) -> None:
        """Configure scheduler with service dependencies."""
        self._redis_service = redis_service
        self._db_service_factory = db_session_factory

    async def start(self) -> None:
        """Start all scheduled tasks."""
        self._running = True

        self._tasks = [
            asyncio.create_task(self._file_cleanup_loop()),
            asyncio.create_task(self._disk_monitor_loop()),
            asyncio.create_task(self._premium_expiry_loop()),
            asyncio.create_task(self._stats_log_loop()),
        ]

        logger.info("Scheduler started with 4 background tasks")

    async def stop(self) -> None:
        """Stop all scheduled tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("Scheduler stopped")

    async def _file_cleanup_loop(self) -> None:
        """
        Periodically clean up expired temporary files.
        Runs every 5 minutes.
        """
        while self._running:
            try:
                await asyncio.sleep(300)  # 5 minutes
                deleted = await self._cleanup_temp_files()
                if deleted > 0:
                    logger.info(f"File cleanup: removed {deleted} expired files")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"File cleanup error: {e}")
                await asyncio.sleep(60)

    async def _cleanup_temp_files(self) -> int:
        """Scan temp directory and remove files older than max TTL."""
        deleted = 0
        max_age = settings.LINK_TTL_MAX_SECONDS + 300  # Extra buffer

        try:
            ensure_dir(settings.TEMP_DIR)
            for filename in os.listdir(settings.TEMP_DIR):
                file_path = os.path.join(settings.TEMP_DIR, filename)
                if not os.path.isfile(file_path):
                    continue
                try:
                    age = os.path.getmtime(file_path)
                    if time.time() - age > max_age:
                        os.remove(file_path)
                        deleted += 1
                except OSError:
                    pass
        except OSError as e:
            logger.error(f"Cleanup scan error: {e}")

        return deleted

    async def _disk_monitor_loop(self) -> None:
        """
        Monitor disk space and log warnings.
        Runs every 2 minutes.
        """
        while self._running:
            try:
                await asyncio.sleep(120)  # 2 minutes
                free_gb = get_disk_free_gb(settings.TEMP_DIR)

                if free_gb < settings.MIN_FREE_DISK_GB:
                    logger.warning(
                        f"LOW DISK SPACE: {free_gb:.2f} GB free "
                        f"(threshold: {settings.MIN_FREE_DISK_GB} GB)"
                    )
                    # Force cleanup
                    await self._cleanup_temp_files()
                elif free_gb < settings.MIN_FREE_DISK_GB * 2:
                    logger.info(f"Disk space warning: {free_gb:.2f} GB free")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Disk monitor error: {e}")
                await asyncio.sleep(60)

    async def _premium_expiry_loop(self) -> None:
        """
        Check for expired premium subscriptions.
        Runs every hour.
        """
        while self._running:
            try:
                await asyncio.sleep(3600)  # 1 hour
                if self._db_service_factory:
                    await self._check_premium_expiries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Premium expiry check error: {e}")
                await asyncio.sleep(300)

    async def _check_premium_expiries(self) -> None:
        """Check and log expired premium subscriptions."""
        try:
            from app.services.database import DatabaseService
            async for session in self._db_service_factory():
                db = DatabaseService(session)
                from sqlalchemy import select
                from app.services.database import UserModel
                now = datetime.now(timezone.utc)

                result = await session.execute(
                    select(UserModel).where(
                        UserModel.premium_expiry.isnot(None),
                        UserModel.premium_expiry > now,
                    )
                )
                active_premium = result.scalars().all()
                logger.debug(f"Active premium users: {len(active_premium)}")
                break
        except Exception as e:
            logger.error(f"Premium expiry DB check error: {e}")

    async def _stats_log_loop(self) -> None:
        """
        Log system statistics periodically.
        Runs every 15 minutes.
        """
        while self._running:
            try:
                await asyncio.sleep(900)  # 15 minutes
                if self._redis_service:
                    total_dl = await self._redis_service.get_global_stat("total_downloads")
                    queues = await self._redis_service.get_queue_lengths()
                    free_gb = get_disk_free_gb(settings.TEMP_DIR)

                    logger.info(
                        f"Stats | Downloads: {total_dl} | "
                        f"Queue H:{queues['high']} N:{queues['normal']} | "
                        f"Disk: {free_gb:.1f}GB free"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stats log error: {e}")
                await asyncio.sleep(300)
