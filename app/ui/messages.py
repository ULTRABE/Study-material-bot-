"""
Message templates using Raven font styling.
All UI text uses Unicode mathematical fonts, no ASCII borders.
"""
from typing import Optional, Dict

from app.utils.fonts import RavenFont


class MessageTemplates:
    """Raven-styled message templates for all bot responses."""

    @staticmethod
    def welcome(first_name: str, is_premium: bool, emoji_map: Dict[str, str]) -> str:
        crown = emoji_map.get("crown", "👑")
        star = emoji_map.get("star", "✨")
        badge = f"{crown} 𝑃𝑟𝑒𝑚𝑖𝑢𝑚" if is_premium else f"{star} 𝐹𝑟𝑒𝑒"
        return (
            f"{RavenFont.BRAND}\n\n"
            f"𝑊𝑒𝑙𝑐𝑜𝑚𝑒, {first_name}\n\n"
            f"𝑆𝑡𝑎𝑡𝑢𝑠  {badge}\n\n"
            f"𝑆𝑒𝑛𝑑 𝑎 𝑑𝑖𝑟𝑒𝑐𝑡 𝑚𝑒𝑑𝑖𝑎 𝑙𝑖𝑛𝑘 𝑡𝑜 𝑏𝑒𝑔𝑖𝑛 𝑝𝑟𝑜𝑐𝑒𝑠𝑠𝑖𝑛𝑔."
        )

    @staticmethod
    def detecting(emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("detecting", "🔎")
        return f"{icon} 𝐿𝑖𝑛𝑘 𝑑𝑒𝑡𝑒𝑐𝑡𝑒𝑑\n\n𝑃𝑟𝑒𝑝𝑎𝑟𝑖𝑛𝑔 𝑡𝑜 𝑝𝑟𝑜𝑐𝑒𝑠𝑠…"

    @staticmethod
    def extracting(emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("extracting", "📂")
        return f"{icon} 𝐸𝑥𝑡𝑟𝑎𝑐𝑡𝑖𝑛𝑔 𝑚𝑒𝑑𝑖𝑎…\n\n𝑅𝑒𝑎𝑑𝑖𝑛𝑔 𝑠𝑡𝑟𝑒𝑎𝑚 𝑖𝑛𝑓𝑜𝑟𝑚𝑎𝑡𝑖𝑜𝑛"

    @staticmethod
    def downloading(percent: int, emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("downloading", "⬇️")
        bar = RavenFont.progress_bar(percent)
        return (
            f"{icon} 𝐷𝑜𝑤𝑛𝑙𝑜𝑎𝑑𝑖𝑛𝑔…\n\n"
            f"{bar}"
        )

    @staticmethod
    def optimizing(percent: int, emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("optimizing", "⚙️")
        bar = RavenFont.progress_bar(percent)
        return (
            f"{icon} 𝑂𝑝𝑡𝑖𝑚𝑖𝑧𝑖𝑛𝑔…\n\n"
            f"{bar}"
        )

    @staticmethod
    def complete(
        file_size: Optional[str],
        emoji_map: Dict[str, str],
    ) -> str:
        check = emoji_map.get("complete", "✅")
        size_line = f"\n𝑆𝑖𝑧𝑒  {file_size}" if file_size else ""
        return f"{check} 𝑅𝑒𝑎𝑑𝑦{size_line}"

    @staticmethod
    def error(reason: str, emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("error", "❌")
        return f"{icon} {reason}"

    @staticmethod
    def blocked_platform(emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("warning", "⚠️")
        return (
            f"{icon} 𝑃𝑙𝑎𝑡𝑓𝑜𝑟𝑚 𝑛𝑜𝑡 𝑠𝑢𝑝𝑝𝑜𝑟𝑡𝑒𝑑.\n\n"
            f"𝑃𝑙𝑒𝑎𝑠𝑒 𝑠𝑒𝑛𝑑 𝑎 𝑑𝑖𝑟𝑒𝑐𝑡 𝑚𝑒𝑑𝑖𝑎 𝑈𝑅𝐿 𝑜𝑛𝑙𝑦."
        )

    @staticmethod
    def premium_required(emoji_map: Dict[str, str]) -> str:
        crown = emoji_map.get("crown", "👑")
        return (
            f"{crown} 𝑃𝑟𝑒𝑚𝑖𝑢𝑚 𝑅𝑒𝑞𝑢𝑖𝑟𝑒𝑑\n\n"
            f"𝑈𝑠𝑒 /𝑟𝑒𝑑𝑒𝑒𝑚 <𝑘𝑒𝑦> 𝑡𝑜 𝑎𝑐𝑡𝑖𝑣𝑎𝑡𝑒 𝑃𝑟𝑒𝑚𝑖𝑢𝑚."
        )

    @staticmethod
    def cooldown(seconds: int, emoji_map: Dict[str, str]) -> str:
        clock = emoji_map.get("clock", "⏳")
        return f"{clock} 𝑃𝑙𝑒𝑎𝑠𝑒 𝑤𝑎𝑖𝑡 {seconds}𝑠 𝑏𝑒𝑓𝑜𝑟𝑒 𝑦𝑜𝑢𝑟 𝑛𝑒𝑥𝑡 𝑟𝑒𝑞𝑢𝑒𝑠𝑡."

    @staticmethod
    def no_credits(emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("warning", "⚠️")
        return (
            f"{icon} 𝐷𝑎𝑖𝑙𝑦 𝑐𝑟𝑒𝑑𝑖𝑡𝑠 𝑒𝑥ℎ𝑎𝑢𝑠𝑡𝑒𝑑.\n\n"
            f"𝐶𝑟𝑒𝑑𝑖𝑡𝑠 𝑟𝑒𝑠𝑒𝑡 𝑒𝑣𝑒𝑟𝑦 24 ℎ𝑜𝑢𝑟𝑠."
        )

    @staticmethod
    def premium_activated(expiry_str: str, emoji_map: Dict[str, str]) -> str:
        crown = emoji_map.get("crown", "👑")
        return (
            f"{crown} 𝑃𝑟𝑒𝑚𝑖𝑢𝑚 𝐴𝑐𝑡𝑖𝑣𝑎𝑡𝑒𝑑\n\n"
            f"𝐸𝑥𝑝𝑖𝑟𝑒𝑠  {expiry_str}"
        )

    @staticmethod
    def key_generated(key: str, duration_days: int, emoji_map: Dict[str, str]) -> str:
        star = emoji_map.get("star", "✨")
        return (
            f"{star} 𝑃𝑟𝑒𝑚𝑖𝑢𝑚 𝐾𝑒𝑦 𝐺𝑒𝑛𝑒𝑟𝑎𝑡𝑒𝑑\n\n"
            f"<code>{key}</code>\n\n"
            f"𝐷𝑢𝑟𝑎𝑡𝑖𝑜𝑛  {duration_days} 𝑑𝑎𝑦𝑠"
        )

    @staticmethod
    def stats(
        total_users: int,
        total_downloads: int,
        active_jobs: int,
        queue_high: int,
        queue_normal: int,
        disk_free_gb: float,
        bot_count: int,
        emoji_map: Dict[str, str],
    ) -> str:
        info = emoji_map.get("info", "ℹ️")
        fire = emoji_map.get("fire", "🔥")
        return (
            f"{RavenFont.BRAND}\n\n"
            f"{info} 𝑆𝑦𝑠𝑡𝑒𝑚 𝑆𝑡𝑎𝑡𝑠\n\n"
            f"𝑈𝑠𝑒𝑟𝑠  {total_users}\n"
            f"𝐷𝑜𝑤𝑛𝑙𝑜𝑎𝑑𝑠  {total_downloads}\n"
            f"{fire} 𝐴𝑐𝑡𝑖𝑣𝑒 𝐽𝑜𝑏𝑠  {active_jobs}\n"
            f"𝑄𝑢𝑒𝑢𝑒  𝐻:{queue_high} 𝑁:{queue_normal}\n"
            f"𝐵𝑜𝑡𝑠  {bot_count}\n"
            f"𝐷𝑖𝑠𝑘  {disk_free_gb:.1f} 𝐺𝐵 𝑓𝑟𝑒𝑒"
        )

    @staticmethod
    def clone_request(bot_username: str, bot_id: int, requester_id: int) -> str:
        return (
            f"{RavenFont.BRAND}\n\n"
            f"𝑁𝑒𝑤 𝐶𝑙𝑜𝑛𝑒 𝑅𝑒𝑞𝑢𝑒𝑠𝑡\n\n"
            f"𝐵𝑜𝑡  @{bot_username}\n"
            f"𝐼𝐷  {bot_id}\n"
            f"𝑅𝑒𝑞𝑢𝑒𝑠𝑡𝑒𝑑 𝑏𝑦  {requester_id}"
        )

    @staticmethod
    def clone_approved(bot_username: str) -> str:
        check = "✅"
        return f"{check} 𝐶𝑙𝑜𝑛𝑒 @{bot_username} 𝑎𝑝𝑝𝑟𝑜𝑣𝑒𝑑 𝑎𝑛𝑑 𝑙𝑖𝑣𝑒."

    @staticmethod
    def clone_declined(bot_username: str) -> str:
        icon = "❌"
        return f"{icon} 𝐶𝑙𝑜𝑛𝑒 @{bot_username} 𝑑𝑒𝑐𝑙𝑖𝑛𝑒𝑑."

    @staticmethod
    def group_authorized(emoji_map: Dict[str, str]) -> str:
        check = emoji_map.get("check", "☑️")
        return f"{check} 𝐺𝑟𝑜𝑢𝑝 𝑎𝑢𝑡ℎ𝑜𝑟𝑖𝑧𝑒𝑑 𝑓𝑜𝑟 𝑚𝑒𝑑𝑖𝑎 𝑝𝑟𝑜𝑐𝑒𝑠𝑠𝑖𝑛𝑔."

    @staticmethod
    def group_not_authorized(emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("warning", "⚠️")
        return (
            f"{icon} 𝑇ℎ𝑖𝑠 𝑔𝑟𝑜𝑢𝑝 𝑖𝑠 𝑛𝑜𝑡 𝑎𝑢𝑡ℎ𝑜𝑟𝑖𝑧𝑒𝑑.\n\n"
            f"𝐴𝑛 𝑎𝑑𝑚𝑖𝑛 𝑚𝑢𝑠𝑡 𝑢𝑠𝑒 /𝑎𝑢𝑡ℎ 𝑡𝑜 𝑒𝑛𝑎𝑏𝑙𝑒 𝑡ℎ𝑖𝑠 𝑔𝑟𝑜𝑢𝑝."
        )

    @staticmethod
    def broadcast_sent(success: int, failed: int, emoji_map: Dict[str, str]) -> str:
        check = emoji_map.get("complete", "✅")
        return (
            f"{check} 𝐵𝑟𝑜𝑎𝑑𝑐𝑎𝑠𝑡 𝐶𝑜𝑚𝑝𝑙𝑒𝑡𝑒\n\n"
            f"𝑆𝑒𝑛𝑡  {success}\n"
            f"𝐹𝑎𝑖𝑙𝑒𝑑  {failed}"
        )

    @staticmethod
    def restart_initiated(emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("optimizing", "⚙️")
        return (
            f"{icon} 𝑅𝑒𝑠𝑡𝑎𝑟𝑡 𝑖𝑛𝑖𝑡𝑖𝑎𝑡𝑒𝑑…\n\n"
            f"𝐺𝑟𝑎𝑐𝑒𝑓𝑢𝑙𝑙𝑦 𝑠ℎ𝑢𝑡𝑡𝑖𝑛𝑔 𝑑𝑜𝑤𝑛 𝑤𝑜𝑟𝑘𝑒𝑟𝑠…"
        )

    @staticmethod
    def assigned_emojis(assignments: Dict[str, str]) -> str:
        lines = [f"{RavenFont.BRAND}\n\n𝐴𝑠𝑠𝑖𝑔𝑛𝑒𝑑 𝐸𝑚𝑜𝑗𝑖𝑠\n"]
        for role, emoji in assignments.items():
            lines.append(f"{emoji}  {role}")
        return "\n".join(lines)

    @staticmethod
    def user_banned(user_id: int, emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("error", "❌")
        return f"{icon} 𝑈𝑠𝑒𝑟 {user_id} ℎ𝑎𝑠 𝑏𝑒𝑒𝑛 𝑏𝑎𝑛𝑛𝑒𝑑."

    @staticmethod
    def user_unbanned(user_id: int, emoji_map: Dict[str, str]) -> str:
        check = emoji_map.get("check", "☑️")
        return f"{check} 𝑈𝑠𝑒𝑟 {user_id} ℎ𝑎𝑠 𝑏𝑒𝑒𝑛 𝑢𝑛𝑏𝑎𝑛𝑛𝑒𝑑."

    @staticmethod
    def not_authorized(emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("error", "❌")
        return f"{icon} 𝑌𝑜𝑢 𝑎𝑟𝑒 𝑛𝑜𝑡 𝑎𝑢𝑡ℎ𝑜𝑟𝑖𝑧𝑒𝑑 𝑡𝑜 𝑢𝑠𝑒 𝑡ℎ𝑖𝑠 𝑐𝑜𝑚𝑚𝑎𝑛𝑑."

    @staticmethod
    def disk_low_warning(free_gb: float, emoji_map: Dict[str, str]) -> str:
        icon = emoji_map.get("warning", "⚠️")
        return (
            f"{icon} 𝐿𝑜𝑤 𝐷𝑖𝑠𝑘 𝑆𝑝𝑎𝑐𝑒\n\n"
            f"𝑂𝑛𝑙𝑦 {free_gb:.1f} 𝐺𝐵 𝑟𝑒𝑚𝑎𝑖𝑛𝑖𝑛𝑔.\n"
            f"𝑁𝑒𝑤 𝑗𝑜𝑏𝑠 𝑎𝑟𝑒 𝑡𝑒𝑚𝑝𝑜𝑟𝑎𝑟𝑖𝑙𝑦 𝑝𝑎𝑢𝑠𝑒𝑑."
        )

    @staticmethod
    def leaderboard(entries: list, emoji_map: Dict[str, str]) -> str:
        fire = emoji_map.get("fire", "🔥")
        lines = [f"{RavenFont.BRAND}\n\n{fire} 𝐿𝑒𝑎𝑑𝑒𝑟𝑏𝑜𝑎𝑟𝑑\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, score) in enumerate(entries[:10]):
            medal = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{medal} 𝑈𝑠𝑒𝑟 {user_id}  {int(score)} 𝑑𝑙")
        return "\n".join(lines)
