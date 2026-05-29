"""Database configuration and session management.

Uses SQLAlchemy async engine with PostgreSQL or local SQLite. The User model is defined here
(rather than in models.py) because fastapi-users requires it at import time
for its dependency chain.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.config import settings
from app.infrastructure.models.base import Base

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 5


if settings.is_sqlite:
    engine_kwargs: dict[str, object] = {"connect_args": {"check_same_thread": False}}
else:
    # Managed Postgres (Railway, Neon, etc.) silently evicts idle TCP
    # connections well before libpq's default keepalive (~2h) kicks in.
    # Without pre-ping / recycle, the pool hands a dead SSL socket to the
    # first checkout after an idle window and the query fails with
    # ``SSL SYSCALL error: EOF detected``. Three layers, in priority order:
    #   1. ``pool_pre_ping`` — ping on checkout, reconnect transparently on
    #      a dead socket. This alone fixes the failure mode.
    #   2. ``pool_recycle`` — proactively tear down connections older than
    #      30 min so they never reach the provider's internal lifetime.
    #   3. ``keepalives*`` — keep the socket warm on the wire so idle
    #      middleboxes (proxies, NAT) never evict it in the first place.
    # ``connect_timeout`` / ``pool_timeout`` bound recovery so a stuck
    # handshake or pool exhaustion fails fast instead of hanging the caller.
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_timeout": 10,
        "connect_args": {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model provided by fastapi-users (id, email, hashed_password, is_active, etc.)."""

    pass


engine = create_async_engine(settings.db_url_async, **engine_kwargs)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db_and_tables() -> None:
    """Create all tables on application startup.

    Every ORM class registers itself with ``Base.metadata`` the moment its
    module loads. By the time the FastAPI lifespan reaches this call, the
    app factory has imported every router, and those routers import the
    compatibility model shims that load ``app.infrastructure.models``.
    Alembic and pytest also load the model shims explicitly. Includes retry
    logic to survive cold-starts from serverless database providers.
    """
    for attempt in range(MAX_RETRIES):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except OperationalError as e:
            if attempt == MAX_RETRIES - 1:
                logger.warning(
                    "Database connection failed after %d attempts: %s. Giving up.",
                    MAX_RETRIES,
                    e,
                )
                raise
            logger.warning(
                "Database connection failed (attempt %d/%d). Retrying in %d seconds...",
                attempt + 1,
                MAX_RETRIES,
                RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_maker() as session:
        yield session


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID]]:
    """FastAPI dependency that yields a fastapi-users database adapter."""
    yield SQLAlchemyUserDatabase(session, User)


__all__ = [
    "Base",
    "User",
    "async_session_maker",
    "create_db_and_tables",
    "engine",
    "get_async_session",
    "get_user_db",
]
