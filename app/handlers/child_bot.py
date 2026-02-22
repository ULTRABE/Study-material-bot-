"""
Child bot handlers: public-facing media processing.
Handles URL detection, processing pipeline, /auth for groups.
"""
import asyncio
import logging
import os
from typing import Optional

from aiogram import Dispatcher, Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.services.database import DatabaseService
from app.services.redis_service import RedisService
from app.services.emoji_service import EmojiService
from app.services.user_service import UserService
from app.ui.messages import MessageTemplates
from app.ui.progress import ProgressEngine
from app.workers.job_models import ProcessingJob, JobStatus
from app.workers.media_processor import MediaProcessor
from app.workers.pool import WorkerPool
from app.utils.helpers import (
    is_blocked_platform,
    is_valid_media_url,
    extract_urls_from_text,
    format_file_size,
    get_disk_free_gb,
)

logger = logging.getLogger(__name__)


def setup_child_handlers(
    dp: Dispatcher,
    db_factory,
    redis_service: RedisService,
    emoji_service: EmojiService,
    worker_pool: WorkerPool,
) -> None:
    """Register all child bot handlers."""
    router = Router()

    async def get_emoji_map() -> dict:
        return await emoji_service.get_all_assigned()

    # ─── /auth (group authorization) ─────────────────────────────────────────

    @router.message(Command("auth"))
    async def cmd_auth(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0

        if user_id not in settings.admin_ids_list:
            emoji_map = await get_emoji_map()
            await message.answer(MessageTemplates.not_authorized(emoji_map), parse_mode="HTML")
            return

        if message.chat.type == "private":
            await message.answer(
                "⚠️ 𝑇ℎ𝑖𝑠 𝑐𝑜𝑚𝑚𝑎𝑛𝑑 𝑚𝑢𝑠𝑡 𝑏𝑒 𝑢𝑠𝑒𝑑 𝑖𝑛 𝑎 𝑔𝑟𝑜𝑢𝑝.",
                parse_mode="HTML",
            )
            return

        bot_id = message.bot.id
        chat_id = message.chat.id

        await redis_service.authorize_group(bot_id, chat_id)

        async for session in db_factory():
            db = DatabaseService(session)
            await db.authorize_group(bot_id, chat_id, user_id)
            break

        emoji_map = await get_emoji_map()
        await message.answer(MessageTemplates.group_authorized(emoji_map), parse_mode="HTML")

    # ─── /status ─────────────────────────────────────────────────────────────

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
            from datetime import timezone
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            expiry_line = f"\n𝐸𝑥𝑝𝑖𝑟𝑒𝑠  {expiry.strftime('%Y-%m-%d')}"

        credits_line = "" if is_premium else f"\n𝐶𝑟𝑒𝑑𝑖𝑡𝑠  {credits}/10"

        from app.utils.fonts import RavenFont
        text = (
            f"{RavenFont.BRAND}\n\n"
            f"𝑆𝑡𝑎𝑡𝑢𝑠  {badge}{expiry_line}\n"
            f"𝐷𝑜𝑤𝑛𝑙𝑜𝑎𝑑𝑠  {user_model.total_downloads}"
            f"{credits_line}\n"
            f"𝐴𝑐𝑡𝑖𝑣𝑒 𝐽𝑜𝑏𝑠  {active_jobs}"
        )
        await message.answer(text, parse_mode="HTML")

    # ─── URL Detection & Processing ───────────────────────────────────────────

    @router.message(F.text)
    async def handle_text(message: Message) -> None:
        """Detect URLs in messages and trigger processing."""
        if message.text is None:
            return

        user = message.from_user
        if user is None:
            return

        # Extract URLs from message
        urls = extract_urls_from_text(message.text)
        if not urls:
            return

        url = urls[0]  # Process first URL only

        emoji_map = await get_emoji_map()

        # Check blocked platforms
        if is_blocked_platform(url):
            await message.answer(
                MessageTemplates.blocked_platform(emoji_map),
                parse_mode="HTML",
            )
            return

        # Validate URL format
        if not is_valid_media_url(url):
            return

        # Check disk space
        free_gb = get_disk_free_gb(settings.TEMP_DIR)
        if free_gb < settings.MIN_FREE_DISK_GB:
            await message.answer(
                MessageTemplates.disk_low_warning(free_gb, emoji_map),
                parse_mode="HTML",
            )
            return

        # Ensure user exists
        is_premium = False
        is_banned = False
        async for session in db_factory():
            db = DatabaseService(session)
            await db.get_or_create_user(
                user.id,
                username=user.username,
                first_name=user.first_name,
            )
            is_premium = await db.is_user_premium(user.id)
            user_obj = await db.get_user(user.id)
            is_banned = user_obj.is_banned if user_obj else False
            break

        if is_banned:
            icon = emoji_map.get("error", "❌")
            await message.answer(
                f"{icon} 𝑌𝑜𝑢 ℎ𝑎𝑣𝑒 𝑏𝑒𝑒𝑛 𝑏𝑎𝑛𝑛𝑒𝑑.",
                parse_mode="HTML",
            )
            return

        is_private = message.chat.type == "private"
        bot_id = message.bot.id

        # Access control checks
        if is_private and not is_premium:
            await message.answer(
                MessageTemplates.premium_required(emoji_map),
                parse_mode="HTML",
            )
            return

        if not is_private:
            authorized = await redis_service.is_group_authorized(bot_id, message.chat.id)
            if not authorized:
                await message.answer(
                    MessageTemplates.group_not_authorized(emoji_map),
                    parse_mode="HTML",
                )
                return

        # Cooldown check (free users)
        if not is_premium:
            if await redis_service.is_on_cooldown(user.id):
                remaining = await redis_service.get_cooldown_remaining(user.id)
                await message.answer(
                    MessageTemplates.cooldown(remaining, emoji_map),
                    parse_mode="HTML",
                )
                return

        # Credit check (free users)
        if not is_premium:
            credits = await redis_service.get_daily_credits(user.id)
            if credits <= 0:
                await message.answer(
                    MessageTemplates.no_credits(emoji_map),
                    parse_mode="HTML",
                )
                return

        # Concurrency check
        active = await redis_service.get_active_jobs(user.id)
        max_jobs = settings.PREMIUM_MAX_CONCURRENT if is_premium else settings.FREE_MAX_CONCURRENT
        if active >= max_jobs:
            icon = emoji_map.get("warning", "⚠️")
            await message.answer(
                f"{icon} 𝑌𝑜𝑢 ℎ𝑎𝑣𝑒 {active} 𝑎𝑐𝑡𝑖𝑣𝑒 𝑗𝑜𝑏(𝑠). 𝑀𝑎𝑥: {max_jobs}.",
                parse_mode="HTML",
            )
            return

        # Duplicate detection
        if await redis_service.check_duplicate_job(user.id, url):
            icon = emoji_map.get("warning", "⚠️")
            await message.answer(
                f"{icon} 𝑇ℎ𝑖𝑠 𝑈𝑅𝐿 𝑖𝑠 𝑎𝑙𝑟𝑒𝑎𝑑𝑦 𝑏𝑒𝑖𝑛𝑔 𝑝𝑟𝑜𝑐𝑒𝑠𝑠𝑒𝑑.",
                parse_mode="HTML",
            )
            return

        # Send initial progress message
        progress_msg = await message.answer(
            MessageTemplates.detecting(emoji_map),
            parse_mode="HTML",
        )

        if progress_msg is None:
            return

        # Create job
        job = ProcessingJob(
            url=url,
            user_id=user.id,
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            bot_token=message.bot.token,
            bot_id=bot_id,
            is_premium=is_premium,
        )

        # Pre-process: consume credit, set cooldown, increment active jobs
        if not is_premium:
            await redis_service.consume_credit(user.id)
            await redis_service.set_cooldown(user.id, settings.FREE_COOLDOWN_SECONDS)
        await redis_service.increment_active_jobs(user.id)
        await redis_service.mark_job_processing(user.id, url)

        # Submit to worker pool
        await worker_pool.submit_job(
            job,
            lambda j: _process_job(
                j,
                message.bot,
                db_factory,
                redis_service,
                emoji_service,
            ),
        )

    async def _process_job(
        job: ProcessingJob,
        bot: Bot,
        db_factory,
        redis_service: RedisService,
        emoji_service: EmojiService,
    ) -> None:
        """Execute the full media processing pipeline for a job."""
        emoji_map = await emoji_service.get_all_assigned()
        progress = ProgressEngine(
            bot=bot,
            chat_id=job.chat_id,
            message_id=job.message_id,
            emoji_map=emoji_map,
        )

        processor = MediaProcessor()
        output_file: Optional[str] = None

        try:
            async def progress_callback(percent: int, stage: str) -> None:
                await progress.update(percent, stage)

            output_file = await processor.process(
                url=job.url,
                job_id=job.job_id,
                progress_callback=progress_callback,
            )

            if output_file is None:
                raise ValueError("Processing returned no output file.")

            # Get file size for caption
            file_size_bytes = 0
            try:
                file_size_bytes = os.path.getsize(output_file)
            except OSError:
                pass
            file_size_str = format_file_size(file_size_bytes) if file_size_bytes > 0 else None

            # Send file directly to user via Telegram
            await progress.finalize_complete(output_file, file_size_str)

            # Log download
            async for session in db_factory():
                db = DatabaseService(session)
                await db.log_download(
                    user_id=job.user_id,
                    bot_id=job.bot_id,
                    url=job.url,
                    file_size_bytes=file_size_bytes,
                    status="completed",
                )
                await db.increment_downloads(job.user_id)
                break

            await redis_service.increment_user_downloads(job.user_id)
            await redis_service.increment_global_stat("total_downloads")

            job.status = JobStatus.COMPLETE

        except Exception as e:
            logger.error(f"Job {job.job_id[:8]} failed: {e}")
            job.status = JobStatus.FAILED
            job.error_message = str(e)

            error_msg = str(e)
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "…"

            await progress.finalize_error(error_msg)

            # Log failed download
            try:
                async for session in db_factory():
                    db = DatabaseService(session)
                    await db.log_download(
                        user_id=job.user_id,
                        bot_id=job.bot_id,
                        url=job.url,
                        status="failed",
                    )
                    break
            except Exception:
                pass

        finally:
            # Always clean up tracking
            await redis_service.decrement_active_jobs(job.user_id)
            await redis_service.unmark_job_processing(job.user_id, job.url)

            # Clean up temp file after sending
            if output_file and os.path.exists(output_file):
                try:
                    os.remove(output_file)
                    logger.debug(f"Cleaned up temp file: {output_file}")
                except OSError:
                    pass

    dp.include_router(router)
