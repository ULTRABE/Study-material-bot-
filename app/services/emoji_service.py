"""
Emoji service: pack ingestion, assignment, randomized retrieval.
"""
import logging
import random
from typing import Dict, List, Optional, Tuple

from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)

# Default emoji roles used throughout the UI
EMOJI_ROLES = [
    "detecting",
    "extracting",
    "downloading",
    "optimizing",
    "complete",
    "error",
    "premium",
    "free",
    "warning",
    "info",
    "star",
    "crown",
    "fire",
    "clock",
    "check",
]

# Default fallback emojis (no custom pack required)
DEFAULT_EMOJIS: Dict[str, str] = {
    "detecting": "🔎",
    "extracting": "📂",
    "downloading": "⬇️",
    "optimizing": "⚙️",
    "complete": "✅",
    "error": "❌",
    "premium": "⭐",
    "free": "🆓",
    "warning": "⚠️",
    "info": "ℹ️",
    "star": "✨",
    "crown": "👑",
    "fire": "🔥",
    "clock": "⏳",
    "check": "☑️",
}


class EmojiService:
    """Manages emoji packs and dynamic emoji assignment."""

    def __init__(self, redis_service: RedisService):
        self.redis = redis_service

    async def ingest_pack(
        self,
        pack_name: str,
        emojis: Dict[str, str],
        progress_callback=None,
    ) -> int:
        """
        Ingest an emoji pack into Redis.
        Returns number of emojis stored.
        """
        total = len(emojis)
        stored = 0
        batch = {}

        for i, (name, emoji_id) in enumerate(emojis.items()):
            batch[name] = emoji_id
            stored += 1

            if progress_callback and (i + 1) % 10 == 0:
                percent = int((i + 1) / total * 100)
                await progress_callback(percent, stored, total)

        await self.redis.store_emoji_pack(pack_name, batch)

        if progress_callback:
            await progress_callback(100, stored, total)

        logger.info(f"Emoji pack '{pack_name}' ingested: {stored} emojis")
        return stored

    async def get_emoji(self, role: str) -> str:
        """
        Get the best emoji for a role.
        Checks assigned emojis first, then random pack, then default.
        """
        # Check assigned emoji
        assigned = await self.redis.get_assigned_emoji(role)
        if assigned:
            return assigned

        # Try random pack
        packs = await self.redis.get_emoji_packs()
        if packs:
            pack_name = random.choice(packs)
            emoji = await self.redis.get_emoji_from_pack(pack_name, role)
            if emoji:
                return emoji

        # Fall back to default
        return DEFAULT_EMOJIS.get(role, "•")

    async def assign_emoji(self, role: str, emoji_data: str) -> None:
        """Assign a specific emoji to a role."""
        await self.redis.set_assigned_emoji(role, emoji_data)
        logger.info(f"Emoji assigned: {role} -> {emoji_data}")

    async def get_all_assigned(self) -> Dict[str, str]:
        """Get all currently assigned emojis."""
        assigned = await self.redis.get_all_assigned_emojis()
        # Fill in defaults for unassigned roles
        result = {}
        for role in EMOJI_ROLES:
            result[role] = assigned.get(role, DEFAULT_EMOJIS.get(role, "•"))
        return result

    async def get_emoji_grid(self) -> List[Tuple[str, str]]:
        """
        Get emoji grid for /assign command display.
        Returns list of (role, current_emoji) tuples.
        """
        assigned = await self.get_all_assigned()
        return [(role, assigned[role]) for role in EMOJI_ROLES]

    async def get_pack_list(self) -> List[str]:
        """Get list of all ingested pack names."""
        return await self.redis.get_emoji_packs()

    async def get_pack_emojis(self, pack_name: str) -> Dict[str, str]:
        """Get all emojis from a specific pack."""
        return await self.redis.get_all_emojis_from_pack(pack_name)

    async def get_random_emoji_for_role(self, role: str) -> str:
        """
        Get a random emoji for a role across all packs.
        If multiple packs have the same role, pick randomly.
        """
        packs = await self.redis.get_emoji_packs()
        candidates = []

        for pack_name in packs:
            emoji = await self.redis.get_emoji_from_pack(pack_name, role)
            if emoji:
                candidates.append(emoji)

        if candidates:
            return random.choice(candidates)

        return DEFAULT_EMOJIS.get(role, "•")
