"""
FastAPI application: webhook routing, file serving, health checks.
Handles all incoming Telegram webhook updates and routes them to the correct bot.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.services.database import init_db, get_db, DatabaseService
from app.services.redis_service import get_redis, RedisService
from app.services.bot_registry import bot_registry
from app.services.emoji_service import EmojiService
from app.services.file_service import FileService
from app.workers.pool import get_worker_pool
from app.scheduler import get_scheduler
from app.utils.helpers import ensure_dir

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # ─── Startup ─────────────────────────────────────────────────────────────
    logger.info("Starting Raven Multi-Bot Platform…")

    # Ensure temp directory exists
    ensure_dir(settings.TEMP_DIR)

    # Initialize database
    await init_db()
    logger.info("✓ Database connected")

    # Initialize Redis
    redis_client = await get_redis()
    redis_service = RedisService(redis_client)
    ping_ok = await redis_service.ping()
    if not ping_ok:
        logger.error("Redis connection failed!")
    else:
        logger.info("✓ Redis connected")

    # Store services in app state
    app.state.redis_service = redis_service
    app.state.emoji_service = EmojiService(redis_service)
    app.state.file_service = FileService(redis_service)

    # Initialize worker pool
    worker_pool = get_worker_pool()
    await worker_pool.start()
    app.state.worker_pool = worker_pool
    logger.info(f"✓ Workers initialized ({settings.WORKER_POOL_SIZE} workers)")

    # Initialize scheduler
    scheduler = get_scheduler()
    scheduler.configure(
        redis_service=redis_service,
        file_service=app.state.file_service,
        db_session_factory=get_db,
    )
    await scheduler.start()
    app.state.scheduler = scheduler

    # Setup mother bot
    await _setup_mother_bot(app)

    # Load existing child bots from database
    await _load_child_bots(app)

    # Register all webhooks
    await bot_registry.register_all_webhooks(settings.BASE_URL)
    logger.info("✓ Webhooks registered")

    logger.info("✓ Bot started successfully")
    logger.info(f"  Mother bot: {settings.BOT_TOKEN[:10]}...")
    logger.info(f"  Base URL: {settings.BASE_URL}")
    logger.info(f"  Active bots: {bot_registry.get_bot_count()}")

    yield

    # ─── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down Raven Multi-Bot Platform…")

    await scheduler.stop()
    await worker_pool.stop()

    # Close all bot sessions
    for token in bot_registry.get_all_tokens():
        bot = bot_registry.get_bot(token)
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass

    logger.info("Shutdown complete")


async def _setup_mother_bot(app: FastAPI) -> None:
    """Initialize and register the mother bot."""
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from app.handlers.mother_bot import setup_mother_handlers
    from app.handlers.common import setup_common_handlers

    mother_bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    mother_dp = Dispatcher()

    # Setup handlers
    setup_common_handlers(
        mother_dp,
        get_db,
        app.state.redis_service,
        app.state.emoji_service,
    )
    setup_mother_handlers(
        mother_dp,
        get_db,
        app.state.redis_service,
        bot_registry,
        app.state.emoji_service,
        app.state.file_service,
        app.state.worker_pool,
        child_dp_factory=lambda dp, bot: _setup_child_dp(
            dp, app.state.redis_service, app.state.emoji_service,
            app.state.file_service, app.state.worker_pool,
        ),
    )

    bot_registry.register_mother(settings.BOT_TOKEN, mother_bot, mother_dp)

    # Store in DB if not exists
    async for session in get_db():
        db = DatabaseService(session)
        bot_info = await mother_bot.get_me()
        existing = await db.get_bot_by_token(settings.BOT_TOKEN)
        if existing is None:
            await db.create_bot(
                bot_id=bot_info.id,
                token=settings.BOT_TOKEN,
                username=bot_info.username,
                is_mother=True,
            )
        break

    logger.info("Mother bot initialized")


async def _load_child_bots(app: FastAPI) -> None:
    """Load all active child bots from database."""
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    active_bots = []
    async for session in get_db():
        db = DatabaseService(session)
        active_bots = await db.get_all_active_bots()
        break

    loaded = 0
    for bot_model in active_bots:
        if bot_model.is_mother or bot_model.token == settings.BOT_TOKEN:
            continue
        if bot_registry.is_registered(bot_model.token):
            continue

        try:
            child_bot = Bot(
                token=bot_model.token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            child_dp = Dispatcher()
            _setup_child_dp(
                child_dp,
                app.state.redis_service,
                app.state.emoji_service,
                app.state.file_service,
                app.state.worker_pool,
            )
            bot_registry.register_child(bot_model.token, child_bot, child_dp)
            loaded += 1
        except Exception as e:
            logger.error(f"Failed to load child bot {bot_model.bot_id}: {e}")

    if loaded > 0:
        logger.info(f"Loaded {loaded} child bot(s) from database")


def _setup_child_dp(
    dp: "Dispatcher",
    redis_service: RedisService,
    emoji_service: EmojiService,
    file_service: FileService,
    worker_pool,
) -> None:
    """Configure a child bot dispatcher with all handlers."""
    from app.handlers.child_bot import setup_child_handlers
    from app.handlers.common import setup_common_handlers

    setup_common_handlers(dp, get_db, redis_service, emoji_service)
    setup_child_handlers(dp, get_db, redis_service, emoji_service, file_service, worker_pool)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Raven Multi-Bot Platform",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    # ─── Webhook Routes ───────────────────────────────────────────────────────

    @app.post("/webhook/{token}")
    async def webhook_handler(token: str, request: Request) -> Response:
        """Handle incoming Telegram webhook updates."""
        # Validate secret token if configured
        if settings.WEBHOOK_SECRET:
            secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if secret != settings.WEBHOOK_SECRET:
                raise HTTPException(status_code=403, detail="Invalid secret token")

        # Find the bot for this token
        bot = bot_registry.get_bot(token)
        dp = bot_registry.get_dispatcher(token)

        if bot is None or dp is None:
            logger.warning(f"Webhook received for unknown token: {token[:10]}...")
            raise HTTPException(status_code=404, detail="Bot not found")

        # Parse and feed update to dispatcher
        try:
            from aiogram.types import Update
            body = await request.json()
            update = Update.model_validate(body)
            await dp.feed_update(bot, update)
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            # Return 200 to prevent Telegram from retrying
        
        return Response(status_code=200)

    # ─── File Serving ─────────────────────────────────────────────────────────

    @app.get("/file/{token}")
    async def serve_file(token: str, request: Request) -> Response:
        """Serve a temporary file by its secure token."""
        file_service: FileService = request.app.state.file_service

        file_path = await file_service.resolve_download_token(token)
        if file_path is None:
            raise HTTPException(
                status_code=404,
                detail="File not found or link has expired.",
            )

        if not os.path.exists(file_path):
            await file_service.invalidate_token(token)
            raise HTTPException(status_code=404, detail="File no longer available.")

        # Determine media type
        ext = os.path.splitext(file_path)[1].lower()
        media_type_map = {
            ".mp4": "video/mp4",
            ".mkv": "video/x-matroska",
            ".avi": "video/x-msvideo",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
            ".mp3": "audio/mpeg",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".wav": "audio/wav",
        }
        media_type = media_type_map.get(ext, "application/octet-stream")
        filename = os.path.basename(file_path)

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    # ─── Health Check ─────────────────────────────────────────────────────────

    @app.get("/health")
    async def health_check(request: Request) -> JSONResponse:
        """System health check endpoint."""
        redis_service: RedisService = request.app.state.redis_service
        worker_pool = request.app.state.worker_pool

        redis_ok = await redis_service.ping()
        pool_stats = worker_pool.get_stats()

        return JSONResponse({
            "status": "ok",
            "redis": "connected" if redis_ok else "disconnected",
            "bots": bot_registry.get_bot_count(),
            "workers": pool_stats,
        })

    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse({"service": "Raven Multi-Bot Platform", "status": "running"})

    return app
