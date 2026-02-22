"""
Security utilities: token generation, validation, key generation.
"""
import secrets
import string
import hashlib
import time
from typing import Optional


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(length)


def generate_premium_key(prefix: str = "RAVEN") -> str:
    """Generate a human-readable premium key."""
    alphabet = string.ascii_uppercase + string.digits
    segments = []
    for _ in range(4):
        segment = "".join(secrets.choice(alphabet) for _ in range(5))
        segments.append(segment)
    return f"{prefix}-" + "-".join(segments)


def validate_token(token: str) -> bool:
    """Basic token format validation."""
    if not token:
        return False
    allowed = set(string.ascii_letters + string.digits + "-_")
    return all(c in allowed for c in token) and 8 <= len(token) <= 128


def hash_token(token: str) -> str:
    """Create a SHA-256 hash of a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_file_token(file_path: str, user_id: int) -> str:
    """Generate a deterministic but secure file access token."""
    seed = f"{file_path}:{user_id}:{time.time()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def is_valid_bot_token(token: str) -> bool:
    """Validate Telegram bot token format: <digits>:<alphanumeric>."""
    if not token or ":" not in token:
        return False
    parts = token.split(":", 1)
    if len(parts) != 2:
        return False
    bot_id_part, secret_part = parts
    if not bot_id_part.isdigit():
        return False
    if len(secret_part) < 20:
        return False
    return True
