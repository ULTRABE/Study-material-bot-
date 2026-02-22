"""
Database service: SQLAlchemy async ORM models and session management.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List, AsyncGenerator

from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean,
    DateTime, Float, Text, UniqueConstraint, Index,
    select, update, delete, func,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


class Base(DeclarativeBase):
    pass


# ─── Models ──────────────────────────────────────────────────────────────────

class BotModel(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(BigInteger, unique=True, nullable=False, index=True)
    token = Column(String(256), unique=True, nullable=False)
    username = Column(String(128), nullable=True)
    status = Column(String(32), default="active", nullable=False)
    is_mother = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(128), nullable=True)
    first_name = Column(String(256), nullable=True)
    is_banned = Column(Boolean, default=False, nullable=False)
    premium_expiry = Column(DateTime, nullable=True)
    total_downloads = Column(Integer, default=0, nullable=False)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PremiumKeyModel(Base):
    __tablename__ = "premium_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    duration_days = Column(Integer, nullable=False)
    used_by = Column(BigInteger, nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(BigInteger, nullable=False)


class AuthorizedGroupModel(Base):
    __tablename__ = "authorized_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(BigInteger, nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False)
    authorized_by = Column(BigInteger, nullable=False)
    authorized_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("bot_id", "chat_id", name="uq_bot_chat"),
    )


class DownloadLogModel(Base):
    __tablename__ = "download_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    bot_id = Column(BigInteger, nullable=False, index=True)
    url = Column(Text, nullable=False)
    file_size_bytes = Column(BigInteger, nullable=True)
    status = Column(String(32), default="completed")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Engine & Session ─────────────────────────────────────────────────────────

async def init_db() -> None:
    """Initialize database engine and create tables."""
    global _engine, _session_factory

    db_url = settings.DATABASE_URL
    # Ensure aiosqlite driver for SQLite
    if db_url.startswith("sqlite:///") and "aiosqlite" not in db_url:
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///")

    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }
    if "postgresql" in db_url:
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20

    _engine = create_async_engine(db_url, **engine_kwargs)

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized successfully")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yield an async database session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class DatabaseService:
    """High-level database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ─── Bot Operations ───────────────────────────────────────────────────────

    async def get_bot(self, bot_id: int) -> Optional[BotModel]:
        result = await self.session.execute(
            select(BotModel).where(BotModel.bot_id == bot_id)
        )
        return result.scalar_one_or_none()

    async def get_bot_by_token(self, token: str) -> Optional[BotModel]:
        result = await self.session.execute(
            select(BotModel).where(BotModel.token == token)
        )
        return result.scalar_one_or_none()

    async def get_all_active_bots(self) -> List[BotModel]:
        result = await self.session.execute(
            select(BotModel).where(BotModel.status == "active")
        )
        return list(result.scalars().all())

    async def create_bot(
        self,
        bot_id: int,
        token: str,
        username: str,
        is_mother: bool = False,
    ) -> BotModel:
        bot = BotModel(
            bot_id=bot_id,
            token=token,
            username=username,
            status="active",
            is_mother=is_mother,
        )
        self.session.add(bot)
        await self.session.flush()
        return bot

    async def update_bot_status(self, bot_id: int, status: str) -> None:
        await self.session.execute(
            update(BotModel)
            .where(BotModel.bot_id == bot_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )

    # ─── User Operations ──────────────────────────────────────────────────────

    async def get_user(self, user_id: int) -> Optional[UserModel]:
        result = await self.session.execute(
            select(UserModel).where(UserModel.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> UserModel:
        user = await self.get_user(user_id)
        if user is None:
            user = UserModel(
                user_id=user_id,
                username=username,
                first_name=first_name,
            )
            self.session.add(user)
            await self.session.flush()
        else:
            user.last_active = datetime.now(timezone.utc)
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
        return user

    async def is_user_premium(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if user is None:
            return False
        if user.premium_expiry is None:
            return False
        now = datetime.now(timezone.utc)
        expiry = user.premium_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry > now

    async def set_premium(self, user_id: int, expiry: datetime) -> None:
        await self.session.execute(
            update(UserModel)
            .where(UserModel.user_id == user_id)
            .values(premium_expiry=expiry)
        )

    async def ban_user(self, user_id: int) -> None:
        await self.session.execute(
            update(UserModel)
            .where(UserModel.user_id == user_id)
            .values(is_banned=True)
        )

    async def unban_user(self, user_id: int) -> None:
        await self.session.execute(
            update(UserModel)
            .where(UserModel.user_id == user_id)
            .values(is_banned=False)
        )

    async def increment_downloads(self, user_id: int) -> None:
        await self.session.execute(
            update(UserModel)
            .where(UserModel.user_id == user_id)
            .values(total_downloads=UserModel.total_downloads + 1)
        )

    async def get_all_user_ids(self) -> List[int]:
        result = await self.session.execute(
            select(UserModel.user_id).where(UserModel.is_banned == False)
        )
        return [row[0] for row in result.fetchall()]

    async def get_user_count(self) -> int:
        result = await self.session.execute(
            select(func.count(UserModel.user_id))
        )
        return result.scalar() or 0

    # ─── Premium Key Operations ───────────────────────────────────────────────

    async def create_premium_key(
        self,
        key: str,
        duration_days: int,
        created_by: int,
    ) -> PremiumKeyModel:
        pk = PremiumKeyModel(
            key=key,
            duration_days=duration_days,
            created_by=created_by,
        )
        self.session.add(pk)
        await self.session.flush()
        return pk

    async def get_premium_key(self, key: str) -> Optional[PremiumKeyModel]:
        result = await self.session.execute(
            select(PremiumKeyModel).where(PremiumKeyModel.key == key)
        )
        return result.scalar_one_or_none()

    async def redeem_premium_key(self, key: str, user_id: int) -> Optional[int]:
        """Redeem a key. Returns duration_days or None if invalid/used."""
        pk = await self.get_premium_key(key)
        if pk is None or pk.used_by is not None:
            return None
        pk.used_by = user_id
        pk.used_at = datetime.now(timezone.utc)
        return pk.duration_days

    # ─── Authorized Groups ────────────────────────────────────────────────────

    async def authorize_group(
        self,
        bot_id: int,
        chat_id: int,
        authorized_by: int,
    ) -> None:
        existing = await self.session.execute(
            select(AuthorizedGroupModel).where(
                AuthorizedGroupModel.bot_id == bot_id,
                AuthorizedGroupModel.chat_id == chat_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            group = AuthorizedGroupModel(
                bot_id=bot_id,
                chat_id=chat_id,
                authorized_by=authorized_by,
            )
            self.session.add(group)

    async def deauthorize_group(self, bot_id: int, chat_id: int) -> None:
        await self.session.execute(
            delete(AuthorizedGroupModel).where(
                AuthorizedGroupModel.bot_id == bot_id,
                AuthorizedGroupModel.chat_id == chat_id,
            )
        )

    async def get_all_authorized_groups(self) -> List[AuthorizedGroupModel]:
        result = await self.session.execute(select(AuthorizedGroupModel))
        return list(result.scalars().all())

    # ─── Download Logs ────────────────────────────────────────────────────────

    async def log_download(
        self,
        user_id: int,
        bot_id: int,
        url: str,
        file_size_bytes: Optional[int] = None,
        status: str = "completed",
    ) -> None:
        log = DownloadLogModel(
            user_id=user_id,
            bot_id=bot_id,
            url=url,
            file_size_bytes=file_size_bytes,
            status=status,
        )
        self.session.add(log)

    async def get_total_downloads(self) -> int:
        result = await self.session.execute(
            select(func.count(DownloadLogModel.id))
        )
        return result.scalar() or 0
