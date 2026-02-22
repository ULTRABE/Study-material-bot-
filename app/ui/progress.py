"""
Progress engine: manages live progress message updates for media processing.
Updates every 5 seconds, never appears stuck.
"""
import asyncio
import logging
import os
from typing import Optional, Dict, Callable, Awaitable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import FSInputFile

from app.ui.messages import MessageTemplates
from app.config import settings

logger = logging.getLogger(__name__)


class ProgressEngine:
    """
    Manages live progress updates for a single processing job.
    Sends updates to Telegram every PROGRESS_UPDATE_INTERVAL seconds.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        emoji_map: Dict[str, str],
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.emoji_map = emoji_map
        self._last_text: Optional[str] = None
        self._update_lock = asyncio.Lock()

    async def update(self, percent: int, stage: str) -> None:
        """
        Update the progress message.
        Stages: detecting, extracting, downloading, optimizing, complete, error
        """
        text = self._build_text(percent, stage)
        if text == self._last_text:
            return

        async with self._update_lock:
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                self._last_text = text
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower():
                    logger.debug(f"Progress update skipped: {e}")
            except Exception as e:
                logger.debug(f"Progress update error: {e}")

    def _build_text(self, percent: int, stage: str) -> str:
        """Build progress message text for a given stage."""
        if stage == "detecting":
            return MessageTemplates.detecting(self.emoji_map)
        elif stage == "extracting":
            return MessageTemplates.extracting(self.emoji_map)
        elif stage == "downloading":
            return MessageTemplates.downloading(percent, self.emoji_map)
        elif stage == "optimizing":
            return MessageTemplates.optimizing(percent, self.emoji_map)
        else:
            return MessageTemplates.detecting(self.emoji_map)

    async def send_initial(self) -> Optional[int]:
        """
        Send the initial progress message.
        Returns the message_id of the sent message.
        """
        text = MessageTemplates.detecting(self.emoji_map)
        try:
            msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
            )
            self.message_id = msg.message_id
            self._last_text = text
            return msg.message_id
        except Exception as e:
            logger.error(f"Failed to send initial progress message: {e}")
            return None

    async def finalize_complete(
        self,
        file_path: str,
        file_size: Optional[str] = None,
    ) -> None:
        """
        Delete the progress message and send the processed file directly to the user.
        """
        check = self.emoji_map.get("complete", "✅")
        caption = f"{check} 𝑅𝑒𝑎𝑑𝑦"
        if file_size:
            caption += f"\n𝑆𝑖𝑧𝑒  {file_size}"

        # Delete the progress message first
        try:
            await self.bot.delete_message(
                chat_id=self.chat_id,
                message_id=self.message_id,
            )
        except Exception:
            pass

        # Send the file directly
        try:
            input_file = FSInputFile(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts"}
            audio_exts = {".mp3", ".aac", ".ogg", ".flac", ".wav", ".m4a"}

            if ext in video_exts:
                await self.bot.send_video(
                    chat_id=self.chat_id,
                    video=input_file,
                    caption=caption,
                    parse_mode="HTML",
                    supports_streaming=True,
                )
            elif ext in audio_exts:
                await self.bot.send_audio(
                    chat_id=self.chat_id,
                    audio=input_file,
                    caption=caption,
                    parse_mode="HTML",
                )
            else:
                await self.bot.send_document(
                    chat_id=self.chat_id,
                    document=input_file,
                    caption=caption,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"Failed to send file to user: {e}")
            # Fallback: send error message
            try:
                error_icon = self.emoji_map.get("error", "❌")
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=f"{error_icon} 𝐹𝑎𝑖𝑙𝑒𝑑 𝑡𝑜 𝑠𝑒𝑛𝑑 𝑓𝑖𝑙𝑒: {str(e)[:200]}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    async def finalize_error(self, reason: str) -> None:
        """Update message to show error."""
        text = MessageTemplates.error(reason, self.emoji_map)
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception:
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
