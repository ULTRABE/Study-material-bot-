"""
Common handlers shared between mother and child bots.
Handles: /start, /help, /redeem, /status
"""
import logging
from datetime import timezone

from aiogram import Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.services.database import DatabaseService
from app.services.redis_service import RedisService
from app.services.emoji_service import EmojiService
from app.services.premium_service import PremiumService
from app.ui.messages import MessageTemplates
from app.utils.fonts import RavenFont

logger = logging.getLogger(__name__)


def setup_common_handlers(
    dp: Dispatcher,
    db_factory,
    redis_service: RedisService,
    emoji_service: EmojiService,
) -> None:
    """Register common handlers on a dispatcher."""
    router = Router()

    async def get_emoji_map() -> dict:
        return await emoji_service.get_all_assigned()

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        user = message.from_user
        if user is None:
            return

        async for session in db_factory():
            db = DatabaseService(session)
            await db.get_or_create_user(
                user.id,
                username=user.username,
                first_name=user.first_name,
            )
            is_premium = await db.is_user_premium(user.id)
            break

        emoji_map = await get_emoji_map()
        text = MessageTemplates.welcome(
            first_name=user.first_name or "User",
            is_premium=is_premium,
            emoji_map=emoji_map,
        )
        await message.answer(text, parse_mode="HTML")

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        emoji_map = await get_emoji_map()
        info = emoji_map.get("info", "ℹ️")
        text = (
            f"{RavenFont.BRAND}\n\n"
            f"{info} 𝐻𝑒𝑙𝑝\n\n"
            f"/start — 𝑆ℎ𝑜𝑤 𝑤𝑒𝑙𝑐𝑜𝑚𝑒\n"
            f"/status — 𝑌𝑜𝑢𝑟 𝑎𝑐𝑐𝑜𝑢𝑛𝑡 𝑠𝑡𝑎𝑡𝑢𝑠\n"
            f"/redeem <𝑘𝑒𝑦> — 𝐴𝑐𝑡𝑖𝑣𝑎𝑡𝑒 𝑃𝑟𝑒𝑚𝑖𝑢𝑚\n\n"
            f"𝑆𝑒𝑛𝑑 𝑎 𝑑𝑖𝑟𝑒𝑐𝑡 𝑚𝑒𝑑𝑖𝑎 𝑈𝑅𝐿 𝑡𝑜 𝑝𝑟𝑜𝑐𝑒𝑠𝑠 𝑖𝑡."
        )
        await message.answer(text, parse_mode="HTML")

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        user = message.from_user
        if user is None:
            return

        async for session in db_factory():
            db = DatabaseService(session)
            user_model = await db.get_or_create_user(user.id)
            is_premium = await db.is_user_premium(user.id)
            break

        emoji_map = await get_emoji_map()
        credits = await redis_service.get_daily_credits(user.id)
        active_jobs = await redis_service.get_active_jobs(user.id)

        crown = emoji_map.get("crown", "👑")
        star = emoji_map.get("star", "✨")
        badge = f"{crown} 𝑃𝑟𝑒𝑚𝑖𝑢𝑚" if is_premium else f"{star} 𝐹𝑟𝑒𝑒"

        expiry_line = ""
        if is_premium and user_model.premium_expiry:
            expiry = user_model.premium_expiry
            if expiry.tzinfo is None:
                from datetime import timezone
                expiry = expiry.replace(tzinfo=timezone.utc)
            expiry_line = f"\n𝐸𝑥𝑝𝑖𝑟𝑒𝑠  {expiry.strftime('%Y-%m-%d')}"

        credits_line = "" if is_premium else f"\n𝐶𝑟𝑒𝑑𝑖𝑡𝑠  {credits}/10"

        text = (
            f"{RavenFont.BRAND}\n\n"
            f"𝑆𝑡𝑎𝑡𝑢𝑠  {badge}{expiry_line}\n"
            f"𝐷𝑜𝑤𝑛𝑙𝑜𝑎𝑑𝑠  {user_model.total_downloads}"
            f"{credits_line}\n"
            f"𝐴𝑐𝑡𝑖𝑣𝑒 𝐽𝑜𝑏𝑠  {active_jobs}"
        )
        await message.answer(text, parse_mode="HTML")

    @router.message(Command("redeem"))
    async def cmd_redeem(message: Message) -> None:
        user = message.from_user
        if user is None:
            return

        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            emoji_map = await get_emoji_map()
            icon = emoji_map.get("info", "ℹ️")
            await message.answer(
                f"{icon} 𝑈𝑠𝑎𝑔𝑒: /𝑟𝑒𝑑𝑒𝑒𝑚 <𝑘𝑒𝑦>",
                parse_mode="HTML",
            )
            return

        key = parts[1].strip().upper()
        emoji_map = await get_emoji_map()

        async for session in db_factory():
            db = DatabaseService(session)
            await db.get_or_create_user(user.id)
            premium_service = PremiumService(db)
            success, msg = await premium_service.redeem_key(key, user.id)
            break

        if success:
            text = MessageTemplates.premium_activated(msg, emoji_map)
        else:
            icon = emoji_map.get("error", "❌")
            text = f"{icon} {msg}"

        await message.answer(text, parse_mode="HTML")

    dp.include_router(router)
