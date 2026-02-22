"""
Inline keyboard builders for all bot interactions.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class Keyboards:
    """Factory for all inline keyboards used in the bot UI."""

    @staticmethod
    def clone_approval(token: str, bot_username: str) -> InlineKeyboardMarkup:
        """Approve/Decline keyboard for clone requests."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"clone:approve:{token}",
            ),
            InlineKeyboardButton(
                text="❌ Decline",
                callback_data=f"clone:decline:{token}",
            ),
        )
        return builder.as_markup()

    @staticmethod
    def restart_confirm() -> InlineKeyboardMarkup:
        """Restart confirmation keyboard."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="♻️ Restart System",
                callback_data="admin:restart:confirm",
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="✖️ Cancel",
                callback_data="admin:restart:cancel",
            ),
        )
        return builder.as_markup()

    @staticmethod
    def emoji_assign_grid(
        roles: list,
        current_emojis: dict,
        page: int = 0,
        per_page: int = 8,
    ) -> InlineKeyboardMarkup:
        """Emoji assignment grid keyboard."""
        builder = InlineKeyboardBuilder()
        start = page * per_page
        end = start + per_page
        page_roles = roles[start:end]

        for role in page_roles:
            emoji = current_emojis.get(role, "•")
            builder.row(
                InlineKeyboardButton(
                    text=f"{emoji} {role}",
                    callback_data=f"emoji:select:{role}",
                )
            )

        # Navigation
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="◀️ Prev",
                    callback_data=f"emoji:page:{page - 1}",
                )
            )
        if end < len(roles):
            nav_buttons.append(
                InlineKeyboardButton(
                    text="Next ▶️",
                    callback_data=f"emoji:page:{page + 1}",
                )
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        return builder.as_markup()

    @staticmethod
    def bot_management(bot_id: int, is_active: bool) -> InlineKeyboardMarkup:
        """Bot enable/disable management keyboard."""
        builder = InlineKeyboardBuilder()
        if is_active:
            builder.row(
                InlineKeyboardButton(
                    text="🔴 Disable Bot",
                    callback_data=f"bot:disable:{bot_id}",
                )
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="🟢 Enable Bot",
                    callback_data=f"bot:enable:{bot_id}",
                )
            )
        return builder.as_markup()

    @staticmethod
    def premium_info(user_id: int) -> InlineKeyboardMarkup:
        """Premium info keyboard with redeem option."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🔑 Redeem Key",
                callback_data=f"premium:redeem:{user_id}",
            )
        )
        return builder.as_markup()

    @staticmethod
    def back_to_main() -> InlineKeyboardMarkup:
        """Simple back button."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="◀️ Back",
                callback_data="nav:main",
            )
        )
        return builder.as_markup()

    @staticmethod
    def confirm_broadcast() -> InlineKeyboardMarkup:
        """Broadcast confirmation keyboard."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="📢 Send Broadcast",
                callback_data="broadcast:confirm",
            ),
            InlineKeyboardButton(
                text="✖️ Cancel",
                callback_data="broadcast:cancel",
            ),
        )
        return builder.as_markup()
