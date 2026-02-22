"""
Redis service: connection management, queue operations, caching.
"""
import json
import logging
from typing import Any, Optional, List, Dict
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Get or create the global Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _redis_client


class RedisService:
    """High-level Redis operations for the Raven platform."""

    # Key prefixes
    PREFIX_USER = "raven:user:"
    PREFIX_BOT = "raven:bot:"
    PREFIX_FILE = "raven:file:"
    PREFIX_JOB = "raven:job:"
    PREFIX_COOLDOWN = "raven:cooldown:"
    PREFIX_CREDITS = "raven:credits:"
    PREFIX_EMOJI = "raven:emoji:"
    PREFIX_GROUP = "raven:group:"
    PREFIX_PENDING_BOT = "raven:pending_bot:"
    PREFIX_ACTIVE_JOBS = "raven:active_jobs:"
    PREFIX_DUPLICATE = "raven:dup:"
    QUEUE_HIGH = "raven:queue:high"
    QUEUE_NORMAL = "raven:queue:normal"
    LEADERBOARD = "raven:leaderboard"

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    # ─── File Token Management ───────────────────────────────────────────────

    async def store_file_token(
        self,
        token: str,
        file_path: str,
        user_id: int,
        ttl: int,
    ) -> None:
        """Store a file token with TTL."""
        key = f"{self.PREFIX_FILE}{token}"
        data = json.dumps({"file_path": file_path, "user_id": user_id})
        await self.redis.setex(key, ttl, data)

    async def get_file_token(self, token: str) -> Optional[Dict]:
        """Retrieve file token data."""
        key = f"{self.PREFIX_FILE}{token}"
        raw = await self.redis.get(key)
        if raw:
            return json.loads(raw)
        return None

    async def delete_file_token(self, token: str) -> None:
        """Invalidate a file token."""
        key = f"{self.PREFIX_FILE}{token}"
        await self.redis.delete(key)

    async def get_file_token_ttl(self, token: str) -> int:
        """Get remaining TTL for a file token in seconds."""
        key = f"{self.PREFIX_FILE}{token}"
        return await self.redis.ttl(key)

    # ─── User Credits ─────────────────────────────────────────────────────────

    async def get_daily_credits(self, user_id: int) -> int:
        """Get remaining daily credits for a user."""
        key = f"{self.PREFIX_CREDITS}{user_id}"
        val = await self.redis.get(key)
        if val is None:
            return settings.FREE_DAILY_CREDITS
        return int(val)

    async def consume_credit(self, user_id: int) -> bool:
        """Consume one credit. Returns False if no credits remain."""
        key = f"{self.PREFIX_CREDITS}{user_id}"
        current = await self.redis.get(key)
        if current is None:
            # Initialize with max - 1
            await self.redis.setex(key, 86400, settings.FREE_DAILY_CREDITS - 1)
            return True
        current_int = int(current)
        if current_int <= 0:
            return False
        await self.redis.decr(key)
        return True

    async def reset_credits(self, user_id: int) -> None:
        """Reset daily credits for a user."""
        key = f"{self.PREFIX_CREDITS}{user_id}"
        await self.redis.setex(key, 86400, settings.FREE_DAILY_CREDITS)

    # ─── Cooldown Management ─────────────────────────────────────────────────

    async def set_cooldown(self, user_id: int, seconds: int) -> None:
        """Set a processing cooldown for a user."""
        key = f"{self.PREFIX_COOLDOWN}{user_id}"
        await self.redis.setex(key, seconds, "1")

    async def is_on_cooldown(self, user_id: int) -> bool:
        """Check if user is on cooldown."""
        key = f"{self.PREFIX_COOLDOWN}{user_id}"
        return await self.redis.exists(key) > 0

    async def get_cooldown_remaining(self, user_id: int) -> int:
        """Get remaining cooldown seconds."""
        key = f"{self.PREFIX_COOLDOWN}{user_id}"
        ttl = await self.redis.ttl(key)
        return max(0, ttl)

    # ─── Active Job Tracking ─────────────────────────────────────────────────

    async def increment_active_jobs(self, user_id: int) -> int:
        """Increment active job count for user. Returns new count."""
        key = f"{self.PREFIX_ACTIVE_JOBS}{user_id}"
        count = await self.redis.incr(key)
        await self.redis.expire(key, 3600)  # Safety TTL
        return count

    async def decrement_active_jobs(self, user_id: int) -> int:
        """Decrement active job count for user."""
        key = f"{self.PREFIX_ACTIVE_JOBS}{user_id}"
        count = await self.redis.decr(key)
        if count < 0:
            await self.redis.set(key, 0)
            return 0
        return count

    async def get_active_jobs(self, user_id: int) -> int:
        """Get current active job count for user."""
        key = f"{self.PREFIX_ACTIVE_JOBS}{user_id}"
        val = await self.redis.get(key)
        return int(val) if val else 0

    # ─── Duplicate Detection ─────────────────────────────────────────────────

    async def check_duplicate_job(self, user_id: int, url: str) -> bool:
        """Return True if this URL is already being processed for this user."""
        key = f"{self.PREFIX_DUPLICATE}{user_id}:{hash(url)}"
        return await self.redis.exists(key) > 0

    async def mark_job_processing(self, user_id: int, url: str, ttl: int = 300) -> None:
        """Mark a URL as being processed."""
        key = f"{self.PREFIX_DUPLICATE}{user_id}:{hash(url)}"
        await self.redis.setex(key, ttl, "1")

    async def unmark_job_processing(self, user_id: int, url: str) -> None:
        """Remove duplicate processing marker."""
        key = f"{self.PREFIX_DUPLICATE}{user_id}:{hash(url)}"
        await self.redis.delete(key)

    # ─── Job Queue ────────────────────────────────────────────────────────────

    async def enqueue_job(self, job_data: Dict, priority: bool = False) -> None:
        """Push a job to the appropriate queue."""
        queue = self.QUEUE_HIGH if priority else self.QUEUE_NORMAL
        await self.redis.rpush(queue, json.dumps(job_data))

    async def dequeue_job(self, timeout: int = 5) -> Optional[Dict]:
        """Pop a job from queues (high priority first)."""
        result = await self.redis.blpop(
            [self.QUEUE_HIGH, self.QUEUE_NORMAL],
            timeout=timeout,
        )
        if result:
            _, raw = result
            return json.loads(raw)
        return None

    async def get_queue_lengths(self) -> Dict[str, int]:
        """Get current queue lengths."""
        high = await self.redis.llen(self.QUEUE_HIGH)
        normal = await self.redis.llen(self.QUEUE_NORMAL)
        return {"high": high, "normal": normal}

    # ─── Bot Registry ─────────────────────────────────────────────────────────

    async def store_pending_bot(self, token: str, bot_info: Dict) -> None:
        """Store a pending bot approval."""
        key = f"{self.PREFIX_PENDING_BOT}{token}"
        await self.redis.setex(key, 3600, json.dumps(bot_info))

    async def get_pending_bot(self, token: str) -> Optional[Dict]:
        """Get pending bot info."""
        key = f"{self.PREFIX_PENDING_BOT}{token}"
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def delete_pending_bot(self, token: str) -> None:
        """Remove pending bot entry."""
        key = f"{self.PREFIX_PENDING_BOT}{token}"
        await self.redis.delete(key)

    # ─── Group Authorization ──────────────────────────────────────────────────

    async def authorize_group(self, bot_id: int, chat_id: int) -> None:
        """Authorize a group for a specific bot."""
        key = f"{self.PREFIX_GROUP}{bot_id}"
        await self.redis.sadd(key, str(chat_id))

    async def deauthorize_group(self, bot_id: int, chat_id: int) -> None:
        """Remove group authorization."""
        key = f"{self.PREFIX_GROUP}{bot_id}"
        await self.redis.srem(key, str(chat_id))

    async def is_group_authorized(self, bot_id: int, chat_id: int) -> bool:
        """Check if a group is authorized for a bot."""
        key = f"{self.PREFIX_GROUP}{bot_id}"
        return await self.redis.sismember(key, str(chat_id))

    async def get_authorized_groups(self, bot_id: int) -> List[int]:
        """Get all authorized groups for a bot."""
        key = f"{self.PREFIX_GROUP}{bot_id}"
        members = await self.redis.smembers(key)
        return [int(m) for m in members]

    # ─── Emoji Storage ────────────────────────────────────────────────────────

    async def store_emoji_pack(self, pack_name: str, emojis: Dict[str, str]) -> None:
        """Store an emoji pack in Redis."""
        key = f"{self.PREFIX_EMOJI}pack:{pack_name}"
        await self.redis.hset(key, mapping=emojis)
        await self.redis.sadd(f"{self.PREFIX_EMOJI}packs", pack_name)

    async def get_emoji_packs(self) -> List[str]:
        """Get all stored emoji pack names."""
        return list(await self.redis.smembers(f"{self.PREFIX_EMOJI}packs"))

    async def get_emoji_from_pack(self, pack_name: str, emoji_name: str) -> Optional[str]:
        """Get a specific emoji from a pack."""
        key = f"{self.PREFIX_EMOJI}pack:{pack_name}"
        return await self.redis.hget(key, emoji_name)

    async def get_all_emojis_from_pack(self, pack_name: str) -> Dict[str, str]:
        """Get all emojis from a pack."""
        key = f"{self.PREFIX_EMOJI}pack:{pack_name}"
        return await self.redis.hgetall(key)

    async def set_assigned_emoji(self, role: str, emoji_data: str) -> None:
        """Assign an emoji to a role."""
        key = f"{self.PREFIX_EMOJI}assigned"
        await self.redis.hset(key, role, emoji_data)

    async def get_assigned_emoji(self, role: str) -> Optional[str]:
        """Get assigned emoji for a role."""
        key = f"{self.PREFIX_EMOJI}assigned"
        return await self.redis.hget(key, role)

    async def get_all_assigned_emojis(self) -> Dict[str, str]:
        """Get all assigned emojis."""
        key = f"{self.PREFIX_EMOJI}assigned"
        return await self.redis.hgetall(key)

    # ─── Leaderboard ─────────────────────────────────────────────────────────

    async def increment_user_downloads(self, user_id: int, count: int = 1) -> None:
        """Increment user's download count in leaderboard."""
        await self.redis.zincrby(self.LEADERBOARD, count, str(user_id))

    async def get_leaderboard(self, top_n: int = 10) -> List[tuple]:
        """Get top N users by download count."""
        return await self.redis.zrevrange(
            self.LEADERBOARD, 0, top_n - 1, withscores=True
        )

    # ─── Stats ────────────────────────────────────────────────────────────────

    async def increment_global_stat(self, stat_name: str, count: int = 1) -> None:
        """Increment a global statistic counter."""
        key = f"raven:stats:{stat_name}"
        await self.redis.incrby(key, count)

    async def get_global_stat(self, stat_name: str) -> int:
        """Get a global statistic value."""
        key = f"raven:stats:{stat_name}"
        val = await self.redis.get(key)
        return int(val) if val else 0

    # ─── Job Progress ─────────────────────────────────────────────────────────

    async def set_job_progress(self, job_id: str, progress_data: Dict) -> None:
        """Store job progress data."""
        key = f"{self.PREFIX_JOB}{job_id}:progress"
        await self.redis.setex(key, 3600, json.dumps(progress_data))

    async def get_job_progress(self, job_id: str) -> Optional[Dict]:
        """Get job progress data."""
        key = f"{self.PREFIX_JOB}{job_id}:progress"
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def delete_job_progress(self, job_id: str) -> None:
        """Remove job progress data."""
        key = f"{self.PREFIX_JOB}{job_id}:progress"
        await self.redis.delete(key)

    # ─── Health Check ─────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            return await self.redis.ping()
        except Exception:
            return False
