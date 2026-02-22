"""
General helper utilities: URL validation, disk checks, platform blocking.
"""
import os
import re
import shutil
from urllib.parse import urlparse
from typing import Optional


# Blocked social media platforms
BLOCKED_DOMAINS = {
    "youtube.com", "youtu.be",
    "facebook.com", "fb.com", "fb.watch",
    "instagram.com",
    "twitter.com", "x.com", "t.co",
    "reddit.com", "redd.it",
    "tiktok.com",
    "vimeo.com",
    "dailymotion.com",
    "twitch.tv",
    "snapchat.com",
    "pinterest.com",
    "linkedin.com",
    "tumblr.com",
    "vine.co",
    "periscope.tv",
    "streamable.com",
    "gfycat.com",
    "giphy.com",
    "tenor.com",
}


def is_blocked_platform(url: str) -> bool:
    """Return True if the URL belongs to a blocked social media platform."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # Strip www. prefix
        if hostname.startswith("www."):
            hostname = hostname[4:]
        # Check exact match and subdomain match
        for blocked in BLOCKED_DOMAINS:
            if hostname == blocked or hostname.endswith(f".{blocked}"):
                return True
        return False
    except Exception:
        return False


def is_valid_media_url(url: str) -> bool:
    """Check if URL is a valid direct media URL."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False


def sanitize_url(url: str) -> str:
    """Strip whitespace and normalize URL."""
    return url.strip()


def format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def get_disk_free_gb(path: str = "/tmp") -> float:
    """Return free disk space in GB for the given path."""
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024 ** 3)
    except Exception:
        return 0.0


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def extract_urls_from_text(text: str) -> list:
    """Extract all URLs from a text string."""
    url_pattern = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+'
    )
    return url_pattern.findall(text)


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to max_length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def ensure_dir(path: str) -> None:
    """Ensure a directory exists, creating it if necessary."""
    os.makedirs(path, exist_ok=True)
