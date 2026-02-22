"""
File service: temporary file management, secure link generation, delivery.
"""
import os
import logging
import asyncio
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.redis_service import RedisService
from app.utils.security import generate_secure_token
from app.utils.helpers import ensure_dir, get_disk_free_gb

logger = logging.getLogger(__name__)


class FileService:
    """Manages temporary media files and secure download links."""

    def __init__(self, redis: RedisService):
        self.redis = redis
        self.temp_dir = settings.TEMP_DIR
        ensure_dir(self.temp_dir)

    def get_temp_path(self, filename: str) -> str:
        """Get full path for a temporary file."""
        return os.path.join(self.temp_dir, filename)

    def has_sufficient_disk_space(self) -> bool:
        """Check if there's enough free disk space."""
        free_gb = get_disk_free_gb(self.temp_dir)
        return free_gb >= settings.MIN_FREE_DISK_GB

    async def create_download_link(
        self,
        file_path: str,
        user_id: int,
        ttl: Optional[int] = None,
    ) -> str:
        """
        Create a secure download link for a file.
        Returns the full download URL.
        """
        token = generate_secure_token(32)
        ttl = ttl or settings.LINK_TTL_SECONDS

        await self.redis.store_file_token(token, file_path, user_id, ttl)

        download_url = f"{settings.file_serve_url}/{token}"
        logger.info(f"Download link created for user {user_id}: token={token[:8]}...")
        return download_url

    async def resolve_download_token(self, token: str) -> Optional[str]:
        """
        Resolve a download token to a file path.
        Returns None if token is invalid or expired.
        """
        data = await self.redis.get_file_token(token)
        if data is None:
            return None
        file_path = data.get("file_path")
        if not file_path or not os.path.exists(file_path):
            await self.redis.delete_file_token(token)
            return None
        return file_path

    async def get_token_ttl(self, token: str) -> int:
        """Get remaining TTL for a download token."""
        return await self.redis.get_file_token_ttl(token)

    async def invalidate_token(self, token: str) -> None:
        """Manually invalidate a download token."""
        await self.redis.delete_file_token(token)

    async def delete_file(self, file_path: str) -> bool:
        """Delete a temporary file from disk."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Deleted temp file: {file_path}")
                return True
            return False
        except OSError as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False

    async def cleanup_expired_files(self) -> int:
        """
        Scan temp directory and remove files older than max TTL.
        Returns number of files deleted.
        """
        deleted = 0
        max_age = settings.LINK_TTL_MAX_SECONDS + 300  # Extra buffer

        try:
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                if not os.path.isfile(file_path):
                    continue
                try:
                    age = os.path.getmtime(file_path)
                    import time
                    if time.time() - age > max_age:
                        os.remove(file_path)
                        deleted += 1
                except OSError:
                    pass
        except OSError as e:
            logger.error(f"Cleanup scan error: {e}")

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired temp files")
        return deleted

    def get_file_size(self, file_path: str) -> int:
        """Get file size in bytes."""
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0

    async def get_disk_stats(self) -> dict:
        """Get disk usage statistics."""
        import shutil
        try:
            usage = shutil.disk_usage(self.temp_dir)
            return {
                "total_gb": usage.total / (1024 ** 3),
                "used_gb": usage.used / (1024 ** 3),
                "free_gb": usage.free / (1024 ** 3),
                "percent_used": (usage.used / usage.total) * 100,
            }
        except Exception:
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent_used": 0}
