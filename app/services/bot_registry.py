"""
Bot Registry: manages active bot instances, dynamic hot-loading, webhook registration.
"""
import logging
from typing import Dict, Optional, List
import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings

logger = logging.getLogger(__name__)


class BotRegistry:
    """
    Central registry for all active bot instances.
    Supports dynamic addition without server restart.
    """

    def __init__(self):
        self._bots: Dict[str, Bot] = {}          # token -> Bot
        self._bot_ids: Dict[int, str] = {}        # bot_id -> token
        self._dispatchers: Dict[str, Dispatcher] = {}  # token -> Dispatcher
        self._mother_token: Optional[str] = None

    def register_mother(self, token: str, bot: Bot, dp: Dispatcher) -> None:
        """Register the mother bot."""
        self._mother_token = token
        self._bots[token] = bot
        self._dispatchers[token] = dp
        logger.info("Mother bot registered")

    def register_child(self, token: str, bot: Bot, dp: Dispatcher) -> None:
        """Register a child bot."""
        self._bots[token] = bot
        self._dispatchers[token] = dp
        logger.info(f"Child bot registered: token prefix {token[:10]}...")

    def get_bot(self, token: str) -> Optional[Bot]:
        """Get bot instance by token."""
        return self._bots.get(token)

    def get_dispatcher(self, token: str) -> Optional[Dispatcher]:
        """Get dispatcher for a token."""
        return self._dispatchers.get(token)

    def get_mother_bot(self) -> Optional[Bot]:
        """Get the mother bot instance."""
        if self._mother_token:
            return self._bots.get(self._mother_token)
        return None

    def get_mother_token(self) -> Optional[str]:
        """Get the mother bot token."""
        return self._mother_token

    def get_all_tokens(self) -> List[str]:
        """Get all registered bot tokens."""
        return list(self._bots.keys())

    def get_all_child_tokens(self) -> List[str]:
        """Get all child bot tokens (excluding mother)."""
        return [t for t in self._bots if t != self._mother_token]

    def is_registered(self, token: str) -> bool:
        """Check if a token is already registered."""
        return token in self._bots

    def remove_bot(self, token: str) -> None:
        """Remove a bot from the registry."""
        self._bots.pop(token, None)
        self._dispatchers.pop(token, None)
        logger.info(f"Bot removed from registry: token prefix {token[:10]}...")

    async def register_webhook(self, token: str, base_url: str) -> bool:
        """Register webhook for a bot token via Telegram API."""
        webhook_url = f"{base_url}/webhook/{token}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {"url": webhook_url}
                if settings.WEBHOOK_SECRET:
                    params["secret_token"] = settings.WEBHOOK_SECRET
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/setWebhook",
                    json=params,
                )
                data = resp.json()
                if data.get("ok"):
                    logger.info(f"Webhook registered: {webhook_url}")
                    return True
                else:
                    logger.error(f"Webhook registration failed: {data}")
                    return False
        except Exception as e:
            logger.error(f"Webhook registration error: {e}")
            return False

    async def delete_webhook(self, token: str) -> bool:
        """Delete webhook for a bot token."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/deleteWebhook"
                )
                data = resp.json()
                return data.get("ok", False)
        except Exception as e:
            logger.error(f"Webhook deletion error: {e}")
            return False

    async def get_bot_info(self, token: str) -> Optional[Dict]:
        """Fetch bot info from Telegram API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{token}/getMe"
                )
                data = resp.json()
                if data.get("ok"):
                    return data["result"]
                return None
        except Exception as e:
            logger.error(f"getMe error for token: {e}")
            return None

    async def register_all_webhooks(self, base_url: str) -> None:
        """Re-register webhooks for all active bots."""
        for token in self._bots:
            await self.register_webhook(token, base_url)

    def get_bot_count(self) -> int:
        """Get total number of registered bots."""
        return len(self._bots)


# Global singleton
bot_registry = BotRegistry()
