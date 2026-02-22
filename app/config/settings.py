import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # Core Bot Settings
    BOT_TOKEN: str
    OWNER_ID: int
    ADMIN_IDS: str = ""

    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379"
    DATABASE_URL: str = "sqlite+aiosqlite:///./raven.db"
    BASE_URL: str = "http://localhost:8000"
    PORT: int = 8000

    # Worker Configuration
    WORKER_POOL_SIZE: int = 8
    MAX_CONCURRENT_JOBS: int = 50
    MAX_CONCURRENT_JOBS_SCALE: int = 100

    # User Limits
    FREE_DAILY_CREDITS: int = 10
    FREE_MAX_CONCURRENT: int = 2
    PREMIUM_MAX_CONCURRENT: int = 5
    FREE_COOLDOWN_SECONDS: int = 30

    # File Settings
    TEMP_DIR: str = "/tmp/raven_media"
    LINK_TTL_MAX_SECONDS: int = 1800  # 30 minutes (used for cleanup only)
    MIN_FREE_DISK_GB: float = 2.0

    # Processing
    MAX_FILE_SIZE_MB: int = 500
    PROGRESS_UPDATE_INTERVAL: int = 5

    # Broadcast
    BROADCAST_BATCH_SIZE: int = 30
    BROADCAST_DELAY_SECONDS: float = 1.0

    # Webhook
    WEBHOOK_SECRET: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def admin_ids_list(self) -> List[int]:
        if not self.ADMIN_IDS:
            return [self.OWNER_ID]
        ids = []
        for part in self.ADMIN_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        if self.OWNER_ID not in ids:
            ids.append(self.OWNER_ID)
        return ids

    @property
    def webhook_url(self) -> str:
        return f"{self.BASE_URL}/webhook"


settings = Settings()
