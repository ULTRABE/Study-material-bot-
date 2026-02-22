"""
User service: access control, credit management, concurrency enforcement.
"""
import logging
from typing import Optional, Tuple

from app.config import settings
from app.services.database import DatabaseService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)


class UserService:
    """Handles user access control, credits, and concurrency."""

    def __init__(self, db: DatabaseService, redis: RedisService):
        self.db = db
        self.redis = redis

    async def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in settings.admin_ids_list

    async def is_owner(self, user_id: int) -> bool:
        """Check if user is the owner."""
        return user_id == settings.OWNER_ID

    async def is_banned(self, user_id: int) -> bool:
        """Check if user is banned."""
        user = await self.db.get_user(user_id)
        return user.is_banned if user else False

    async def is_premium(self, user_id: int) -> bool:
        """Check if user has active premium."""
        return await self.db.is_user_premium(user_id)

    async def get_max_concurrent(self, user_id: int) -> int:
        """Get max concurrent jobs for user."""
        if await self.is_premium(user_id):
            return settings.PREMIUM_MAX_CONCURRENT
        return settings.FREE_MAX_CONCURRENT

    async def can_process(
        self,
        user_id: int,
        chat_id: int,
        bot_id: int,
        is_private: bool,
    ) -> Tuple[bool, str]:
        """
        Check if user can submit a processing job.
        Returns (allowed, reason_if_denied).
        """
        # Check ban
        if await self.is_banned(user_id):
            return False, "You have been banned from using this service."

        is_prem = await self.is_premium(user_id)

        # Private chat: premium only
        if is_private and not is_prem:
            return False, (
                "Private chat processing requires Premium.\n"
                "Use the bot in a group or upgrade to Premium."
            )

        # Group authorization check
        if not is_private:
            authorized = await self.redis.is_group_authorized(bot_id, chat_id)
            if not authorized:
                return False, (
                    "This group is not authorized for media processing.\n"
                    "An admin must use /auth to authorize this group."
                )

        # Cooldown check (free users only)
        if not is_prem:
            if await self.redis.is_on_cooldown(user_id):
                remaining = await self.redis.get_cooldown_remaining(user_id)
                return False, f"Please wait {remaining}s before your next request."

        # Credit check (free users only)
        if not is_prem:
            credits = await self.redis.get_daily_credits(user_id)
            if credits <= 0:
                return False, (
                    "You've used all your daily credits (10/day).\n"
                    "Credits reset every 24 hours. Upgrade to Premium for unlimited access."
                )

        # Concurrency check
        active = await self.redis.get_active_jobs(user_id)
        max_jobs = await self.get_max_concurrent(user_id)
        if active >= max_jobs:
            return False, (
                f"You already have {active} active job(s). "
                f"Maximum is {max_jobs} for your plan."
            )

        return True, ""

    async def pre_process_user(self, user_id: int) -> None:
        """
        Perform pre-processing actions:
        - Consume credit (free users)
        - Set cooldown (free users)
        - Increment active jobs
        """
        is_prem = await self.is_premium(user_id)

        if not is_prem:
            await self.redis.consume_credit(user_id)
            await self.redis.set_cooldown(user_id, settings.FREE_COOLDOWN_SECONDS)

        await self.redis.increment_active_jobs(user_id)

    async def post_process_user(self, user_id: int, success: bool = True) -> None:
        """
        Perform post-processing actions:
        - Decrement active jobs
        - Increment download count if successful
        """
        await self.redis.decrement_active_jobs(user_id)

        if success:
            await self.db.increment_downloads(user_id)
            await self.redis.increment_user_downloads(user_id)
            await self.redis.increment_global_stat("total_downloads")

    async def ensure_user_exists(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> None:
        """Ensure user record exists in database."""
        await self.db.get_or_create_user(user_id, username, first_name)
