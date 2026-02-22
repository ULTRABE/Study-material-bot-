"""
Raven Multi-Bot Platform — Entry Point
Starts the FastAPI/uvicorn server in webhook mode.
"""
import logging
import os
import sys

import uvicorn

from app.api.app import create_app
from app.config import settings

# ─── Logging Configuration ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Suppress noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    """Start the Raven platform."""
    app = create_app()

    logger.info("=" * 60)
    logger.info("  Raven Multi-Bot Platform v1.0.0")
    logger.info("=" * 60)
    logger.info(f"  Port:     {settings.PORT}")
    logger.info(f"  Base URL: {settings.BASE_URL}")
    logger.info(f"  Workers:  {settings.WORKER_POOL_SIZE}")
    logger.info(f"  Max Jobs: {settings.MAX_CONCURRENT_JOBS}")
    logger.info("=" * 60)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info",
        access_log=False,
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
