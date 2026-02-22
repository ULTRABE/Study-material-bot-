"""
Mother bot handlers: admin-only commands for system management.
Commands: /clone, /genkey, /approve, /ban, /unban, /broadcast,
          /stats, /assign, /assigned, /restart, /disable_bot, /enable_bot, /auth
"""
import asyncio
import logging
from typing import Optional

from aiogram import Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import settings
from app.services.database import DatabaseService
from app.services.redis_service import RedisService
from app.services.bot_registry import BotRegistry
from app.services.emoji_service import EmojiService, EMOJI_ROLES
from app.services.premium_service import PremiumService
from app.services.file_service import FileService
from app.ui.messages import MessageTemplates
from app.ui.keyboards import Keyboards
from app.utils.security import is_valid_bot_token
from app.utils.helpers import get_disk_free_gb
from app.workers.pool import WorkerPool

logger = logging.getLogger(__name__)


def setup_mother_handlers(
    dp: Dispatcher,
    db_factory,
    redis_service: RedisService,
    bot_registry: BotRegistry,
    emoji_service: EmojiService,
    file_service: FileService,
    worker_pool: WorkerPool,
    child_dp_factory,
) -> None:
    """Register all mother bot handlers."""
    router = Router()

    async def get_emoji_map() -> dict:
        return await emoji_service.get_all_assigned()

    def is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids_list

    # ─── /clone ──────────────────────────────────────────────────────────────

    @router.message(Command("clone"))
    async def cmd_clone(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("𝑈𝑠𝑎𝑔𝑒: /𝑐𝑙𝑜𝑛𝑒 <𝑏𝑜𝑡_𝑡𝑜𝑘𝑒𝑛>", parse_mode="HTML")
            return

        token = parts[1].strip()
        if not is_valid_bot_token(token):
            await message.answer("❌ 𝐼𝑛𝑣𝑎𝑙𝑖𝑑 𝑏𝑜𝑡 𝑡𝑜𝑘𝑒𝑛 𝑓𝑜𝑟𝑚𝑎𝑡.", parse_mode="HTML")
            return

        if bot_registry.is_registered(token):
            await message.answer("⚠️ 𝑇ℎ𝑖𝑠 𝑏𝑜𝑡 𝑖𝑠 𝑎𝑙𝑟𝑒𝑎𝑑𝑦 𝑟𝑒𝑔𝑖𝑠𝑡𝑒𝑟𝑒𝑑.", parse_mode="HTML")
            return

        # Validate token via Telegram API
        bot_info = await bot_registry.get_bot_info(token)
        if bot_info is None:
            await message.answer("❌ 𝐶𝑜𝑢𝑙𝑑 𝑛𝑜𝑡 𝑣𝑎𝑙𝑖𝑑𝑎𝑡𝑒 𝑡𝑜𝑘𝑒𝑛 𝑤𝑖𝑡ℎ 𝑇𝑒𝑙𝑒𝑔𝑟𝑎𝑚.", parse_mode="HTML")
            return

        # Store in pending registry
        pending_data = {
            "token": token,
            "bot_id": bot_info["id"],
            "username": bot_info.get("username", "unknown"),
            "requester_id": message.from_user.id,
        }
        await redis_service.store_pending_bot(token, pending_data)

        # Notify owner
        text = MessageTemplates.clone_request(
            bot_username=bot_info.get("username", "unknown"),
            bot_id=bot_info["id"],
            requester_id=message.from_user.id,
        )
        keyboard = Keyboards.clone_approval(token, bot_info.get("username", ""))

        mother_bot = bot_registry.get_mother_bot()
        if mother_bot:
            await mother_bot.send_message(
                chat_id=settings.OWNER_ID,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        await message.answer("✅ 𝐶𝑙𝑜𝑛𝑒 𝑟𝑒𝑞𝑢𝑒𝑠𝑡 𝑠𝑒𝑛𝑡 𝑓𝑜𝑟 𝑎𝑝𝑝𝑟𝑜𝑣𝑎𝑙.", parse_mode="HTML")

    # ─── Clone Approval Callbacks ─────────────────────────────────────────────

    @router.callback_query(F.data.startswith("clone:approve:"))
    async def cb_clone_approve(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            await callback.answer("Not authorized", show_alert=True)
            return

        token = callback.data.split(":", 2)[2]
        pending = await redis_service.get_pending_bot(token)

        if pending is None:
            await callback.answer("Request expired or not found.", show_alert=True)
            return

        await redis_service.delete_pending_bot(token)

        # Register the child bot
        try:
            from aiogram import Bot, Dispatcher as AiogramDP
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode

            child_bot = Bot(
                token=token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            child_dp = AiogramDP()

            # Setup child handlers
            child_dp_factory(child_dp, child_bot)

            bot_registry.register_child(token, child_bot, child_dp)

            # Register webhook
            await bot_registry.register_webhook(token, settings.BASE_URL)

            # Store in database
            async for session in db_factory():
                db = DatabaseService(session)
                existing = await db.get_bot_by_token(token)
                if existing is None:
                    await db.create_bot(
                        bot_id=pending["bot_id"],
                        token=token,
                        username=pending["username"],
                        is_mother=False,
                    )
                break

            text = MessageTemplates.clone_approved(pending["username"])
            await callback.message.edit_text(text, parse_mode="HTML")
            await callback.answer("Bot approved and live!")

            logger.info(f"Clone approved: @{pending['username']} (ID: {pending['bot_id']})")

        except Exception as e:
            logger.error(f"Clone approval error: {e}")
            await callback.answer(f"Error: {str(e)[:100]}", show_alert=True)

    @router.callback_query(F.data.startswith("clone:decline:"))
    async def cb_clone_decline(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            await callback.answer("Not authorized", show_alert=True)
            return

        token = callback.data.split(":", 2)[2]
        pending = await redis_service.get_pending_bot(token)

        if pending:
            await redis_service.delete_pending_bot(token)
            text = MessageTemplates.clone_declined(pending.get("username", "unknown"))
        else:
            text = "❌ 𝑅𝑒𝑞𝑢𝑒𝑠𝑡 𝑛𝑜𝑡 𝑓𝑜𝑢𝑛𝑑."

        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer("Bot declined.")

    # ─── /genkey ─────────────────────────────────────────────────────────────

    @router.message(Command("genkey"))
    async def cmd_genkey(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        parts = message.text.split() if message.text else []
        duration_days = 30  # Default
        if len(parts) >= 2:
            try:
                duration_days = int(parts[1])
            except ValueError:
                await message.answer("❌ 𝐼𝑛𝑣𝑎𝑙𝑖𝑑 𝑑𝑢𝑟𝑎𝑡𝑖𝑜𝑛. 𝑈𝑠𝑒: /𝑔𝑒𝑛𝑘𝑒𝑦 <𝑑𝑎𝑦𝑠>", parse_mode="HTML")
                return

        async for session in db_factory():
            db = DatabaseService(session)
            premium_service = PremiumService(db)
            key = await premium_service.generate_key(duration_days, message.from_user.id)
            break

        emoji_map = await get_emoji_map()
        text = MessageTemplates.key_generated(key, duration_days, emoji_map)
        await message.answer(text, parse_mode="HTML")

    # ─── /ban and /unban ─────────────────────────────────────────────────────

    @router.message(Command("ban"))
    async def cmd_ban(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        parts = message.text.split() if message.text else []
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("𝑈𝑠𝑎𝑔𝑒: /𝑏𝑎𝑛 <𝑢𝑠𝑒𝑟_𝑖𝑑>", parse_mode="HTML")
            return

        target_id = int(parts[1])
        async for session in db_factory():
            db = DatabaseService(session)
            await db.get_or_create_user(target_id)
            await db.ban_user(target_id)
            break

        emoji_map = await get_emoji_map()
        await message.answer(MessageTemplates.user_banned(target_id, emoji_map), parse_mode="HTML")

    @router.message(Command("unban"))
    async def cmd_unban(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        parts = message.text.split() if message.text else []
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("𝑈𝑠𝑎𝑔𝑒: /𝑢𝑛𝑏𝑎𝑛 <𝑢𝑠𝑒𝑟_𝑖𝑑>", parse_mode="HTML")
            return

        target_id = int(parts[1])
        async for session in db_factory():
            db = DatabaseService(session)
            await db.unban_user(target_id)
            break

        emoji_map = await get_emoji_map()
        await message.answer(MessageTemplates.user_unbanned(target_id, emoji_map), parse_mode="HTML")

    # ─── /broadcast ──────────────────────────────────────────────────────────

    @router.message(Command("broadcast"))
    async def cmd_broadcast(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("𝑈𝑠𝑎𝑔𝑒: /𝑏𝑟𝑜𝑎𝑑𝑐𝑎𝑠𝑡 <𝑚𝑒𝑠𝑠𝑎𝑔𝑒>", parse_mode="HTML")
            return

        broadcast_text = parts[1].strip()
        status_msg = await message.answer("📢 𝑆𝑡𝑎𝑟𝑡𝑖𝑛𝑔 𝑏𝑟𝑜𝑎𝑑𝑐𝑎𝑠𝑡…", parse_mode="HTML")

        # Run broadcast in background
        asyncio.create_task(
            _run_broadcast(
                broadcast_text,
                message.bot,
                db_factory,
                redis_service,
                bot_registry,
                emoji_service,
                status_msg,
            )
        )

    async def _run_broadcast(
        text: str,
        mother_bot,
        db_factory,
        redis_service: RedisService,
        bot_registry: BotRegistry,
        emoji_service: EmojiService,
        status_msg,
    ) -> None:
        """Execute broadcast to all users across all bots."""
        success = 0
        failed = 0
        user_ids = []

        async for session in db_factory():
            db = DatabaseService(session)
            user_ids = await db.get_all_user_ids()
            break

        all_tokens = bot_registry.get_all_tokens()
        batch_size = settings.BROADCAST_BATCH_SIZE

        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]
            for user_id in batch:
                for token in all_tokens:
                    bot = bot_registry.get_bot(token)
                    if bot:
                        try:
                            await bot.send_message(
                                chat_id=user_id,
                                text=text,
                                parse_mode="HTML",
                            )
                            success += 1
                            break  # Only send once per user
                        except Exception:
                            failed += 1
                            break

            await asyncio.sleep(settings.BROADCAST_DELAY_SECONDS)

        # Also send to authorized groups
        groups = []
        async for session in db_factory():
            db = DatabaseService(session)
            groups = await db.get_all_authorized_groups()
            break

        for group in groups:
            bot = bot_registry.get_mother_bot()
            if bot:
                try:
                    await bot.send_message(
                        chat_id=group.chat_id,
                        text=text,
                        parse_mode="HTML",
                    )
                    success += 1
                except Exception:
                    failed += 1

        emoji_map = await emoji_service.get_all_assigned()
        result_text = MessageTemplates.broadcast_sent(success, failed, emoji_map)
        try:
            await status_msg.edit_text(result_text, parse_mode="HTML")
        except Exception:
            pass

    # ─── /stats ──────────────────────────────────────────────────────────────

    @router.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        async for session in db_factory():
            db = DatabaseService(session)
            total_users = await db.get_user_count()
            total_downloads = await db.get_total_downloads()
            break

        queues = await redis_service.get_queue_lengths()
        pool_stats = worker_pool.get_stats()
        disk_stats = await file_service.get_disk_stats()
        emoji_map = await get_emoji_map()

        text = MessageTemplates.stats(
            total_users=total_users,
            total_downloads=total_downloads,
            active_jobs=pool_stats["active_jobs"],
            queue_high=queues["high"],
            queue_normal=queues["normal"],
            disk_free_gb=disk_stats["free_gb"],
            bot_count=bot_registry.get_bot_count(),
            emoji_map=emoji_map,
        )
        await message.answer(text, parse_mode="HTML")

    # ─── /assign ─────────────────────────────────────────────────────────────

    @router.message(Command("assign"))
    async def cmd_assign(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        emoji_map = await get_emoji_map()
        keyboard = Keyboards.emoji_assign_grid(EMOJI_ROLES, emoji_map, page=0)
        await message.answer(
            f"𝑆𝑒𝑙𝑒𝑐𝑡 𝑎 𝑟𝑜𝑙𝑒 𝑡𝑜 𝑎𝑠𝑠𝑖𝑔𝑛 𝑎𝑛 𝑒𝑚𝑜𝑗𝑖:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith("emoji:page:"))
    async def cb_emoji_page(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            await callback.answer("Not authorized", show_alert=True)
            return

        page = int(callback.data.split(":")[2])
        emoji_map = await get_emoji_map()
        keyboard = Keyboards.emoji_assign_grid(EMOJI_ROLES, emoji_map, page=page)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer()

    @router.callback_query(F.data.startswith("emoji:select:"))
    async def cb_emoji_select(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            await callback.answer("Not authorized", show_alert=True)
            return

        role = callback.data.split(":", 2)[2]
        await callback.message.edit_text(
            f"𝑆𝑒𝑛𝑑 𝑡ℎ𝑒 𝑒𝑚𝑜𝑗𝑖 𝑡𝑜 𝑎𝑠𝑠𝑖𝑔𝑛 𝑡𝑜 𝑟𝑜𝑙𝑒: <b>{role}</b>\n\n"
            f"𝑅𝑒𝑝𝑙𝑦 𝑤𝑖𝑡ℎ 𝑡ℎ𝑒 𝑒𝑚𝑜𝑗𝑖 𝑐ℎ𝑎𝑟𝑎𝑐𝑡𝑒𝑟 𝑜𝑟 𝑐𝑢𝑠𝑡𝑜𝑚 𝑒𝑚𝑜𝑗𝑖 𝐼𝐷.",
            parse_mode="HTML",
        )
        # Store pending assignment in Redis
        await redis_service.redis.setex(
            f"raven:emoji:pending:{callback.from_user.id}",
            300,
            role,
        )
        await callback.answer()

    @router.message(F.text & ~F.text.startswith("/"))
    async def handle_emoji_assignment(message: Message) -> None:
        """Handle emoji assignment replies."""
        if not is_admin(message.from_user.id):
            return

        pending_role = await redis_service.redis.get(
            f"raven:emoji:pending:{message.from_user.id}"
        )
        if pending_role and message.text:
            await emoji_service.assign_emoji(pending_role, message.text.strip())
            await redis_service.redis.delete(f"raven:emoji:pending:{message.from_user.id}")
            emoji_map = await get_emoji_map()
            check = emoji_map.get("check", "☑️")
            await message.answer(
                f"{check} 𝐸𝑚𝑜𝑗𝑖 𝑎𝑠𝑠𝑖𝑔𝑛𝑒𝑑 𝑡𝑜 𝑟𝑜𝑙𝑒: {pending_role}",
                parse_mode="HTML",
            )

    # ─── /assigned ───────────────────────────────────────────────────────────

    @router.message(Command("assigned"))
    async def cmd_assigned(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        assignments = await emoji_service.get_all_assigned()
        text = MessageTemplates.assigned_emojis(assignments)
        await message.answer(text, parse_mode="HTML")

    # ─── /restart ────────────────────────────────────────────────────────────

    @router.message(Command("restart"))
    async def cmd_restart(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        keyboard = Keyboards.restart_confirm()
        await message.answer(
            "⚠️ 𝐶𝑜𝑛𝑓𝑖𝑟𝑚 𝑠𝑦𝑠𝑡𝑒𝑚 𝑟𝑒𝑠𝑡𝑎𝑟𝑡?",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "admin:restart:confirm")
    async def cb_restart_confirm(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            await callback.answer("Not authorized", show_alert=True)
            return

        emoji_map = await get_emoji_map()
        text = MessageTemplates.restart_initiated(emoji_map)
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()

        # Graceful restart sequence
        asyncio.create_task(_perform_restart(worker_pool, bot_registry))

    @router.callback_query(F.data == "admin:restart:cancel")
    async def cb_restart_cancel(callback: CallbackQuery) -> None:
        await callback.message.edit_text("✖️ 𝑅𝑒𝑠𝑡𝑎𝑟𝑡 𝑐𝑎𝑛𝑐𝑒𝑙𝑙𝑒𝑑.", parse_mode="HTML")
        await callback.answer()

    async def _perform_restart(worker_pool: WorkerPool, bot_registry: BotRegistry) -> None:
        """Perform graceful restart sequence."""
        import os
        import sys

        logger.info("Restart initiated by admin")

        # Flush queues
        await worker_pool.flush_queues()

        # Re-register all webhooks
        await bot_registry.register_all_webhooks(settings.BASE_URL)

        logger.info("Restart sequence complete — re-registering webhooks")

        # Signal process restart (Railway will restart the container)
        await asyncio.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ─── /disable_bot and /enable_bot ────────────────────────────────────────

    @router.message(Command("disable_bot"))
    async def cmd_disable_bot(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        parts = message.text.split() if message.text else []
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("𝑈𝑠𝑎𝑔𝑒: /𝑑𝑖𝑠𝑎𝑏𝑙𝑒_𝑏𝑜𝑡 <𝑏𝑜𝑡_𝑖𝑑>", parse_mode="HTML")
            return

        bot_id = int(parts[1])
        async for session in db_factory():
            db = DatabaseService(session)
            await db.update_bot_status(bot_id, "disabled")
            break

        await message.answer(f"🔴 𝐵𝑜𝑡 {bot_id} 𝑑𝑖𝑠𝑎𝑏𝑙𝑒𝑑.", parse_mode="HTML")

    @router.message(Command("enable_bot"))
    async def cmd_enable_bot(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        parts = message.text.split() if message.text else []
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("𝑈𝑠𝑎𝑔𝑒: /𝑒𝑛𝑎𝑏𝑙𝑒_𝑏𝑜𝑡 <𝑏𝑜𝑡_𝑖𝑑>", parse_mode="HTML")
            return

        bot_id = int(parts[1])
        async for session in db_factory():
            db = DatabaseService(session)
            await db.update_bot_status(bot_id, "active")
            break

        await message.answer(f"🟢 𝐵𝑜𝑡 {bot_id} 𝑒𝑛𝑎𝑏𝑙𝑒𝑑.", parse_mode="HTML")

    # ─── /auth ────────────────────────────────────────────────────────────────

    @router.message(Command("auth"))
    async def cmd_auth(message: Message) -> None:
        if not is_admin(message.from_user.id):
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map))
            return

        if message.chat.type == "private":
            await message.answer("⚠️ 𝑇ℎ𝑖𝑠 𝑐𝑜𝑚𝑚𝑎𝑛𝑑 𝑚𝑢𝑠𝑡 𝑏𝑒 𝑢𝑠𝑒𝑑 𝑖𝑛 𝑎 𝑔𝑟𝑜𝑢𝑝.", parse_mode="HTML")
            return

        bot_id = message.bot.id
        chat_id = message.chat.id

        await redis_service.authorize_group(bot_id, chat_id)

        async for session in db_factory():
            db = DatabaseService(session)
            await db.authorize_group(bot_id, chat_id, message.from_user.id)
            break

        emoji_map = await get_emoji_map()
        await message.answer(MessageTemplates.group_authorized(emoji_map), parse_mode="HTML")

    dp.include_router(router)
