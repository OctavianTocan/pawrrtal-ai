"""Shared backend test fixtures."""

import os
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from uuid import uuid4

# Exclude live-backend E2E tests from default collection. They boot a real
# uvicorn subprocess and only make sense behind the ``PAW_E2E=1`` gate;
# without the gate, pytest would try to import their conftest and skip at
# module level, which still adds load time and noise. Skipping the whole
# directory here keeps the default ``uv run pytest`` run fast and offline.
collect_ignore_glob: list[str] = []
if os.environ.get("PAW_E2E") != "1":
    collect_ignore_glob.append("e2e_paw/*")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.infrastructure.logging.setup import configure_logging

configure_logging()

from app import models  # noqa: F401  # Registers ORM models on Base metadata.
from app.infrastructure.auth.users import current_active_user
from app.infrastructure.database.legacy import User, get_async_session
from app.infrastructure.models.base import Base
from app.models import Workspace
from main import create_app


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-powered async tests on asyncio only."""
    return "asyncio"


@pytest.fixture
def test_user() -> User:
    """Return an active user for request dependency overrides."""
    return User(
        id=uuid4(),
        email="tester@example.com",
        hashed_password="not-used",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )


@pytest.fixture
async def db_session(
    test_user: User, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncSession]:
    """Provide an isolated in-memory SQLite database session.

    Also rebinds ``app.channels.turn_runner.async_session_maker`` to this
    in-memory engine so background helpers in the chat turn runner
    (``_turn_session``, ``load_codex_thread_id``, ``persist_codex_thread_id``)
    see the same tables the request session sees. Required because the chat
    router intentionally does NOT pass the request-scoped session into
    ``ChatTurnInput`` — see ``tests/test_chat_sqlite_session_lifecycle.py``
    and the comment in ``app/api/chat.py`` for the SQLite/aiosqlite lifecycle
    rationale.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    # The turn runner opens its own sessions for the streaming/finalization
    # path so the route handler's dependency cleanup can't tear the
    # connection out from under it (a SQLite/aiosqlite-specific failure
    # mode). In tests, point those calls at the in-memory engine so the
    # runner sees the same tables and seeded rows as the request session.
    monkeypatch.setattr("app.channels.turn_runner.async_session_maker", session_maker, raising=True)
    async with session_maker() as session:
        session.add(test_user)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.fixture
async def seeded_default_workspace(
    db_session: AsyncSession, test_user: User, tmp_path: Path
) -> Workspace:
    """Seed a default workspace for tests that need an onboarded user.

    Chat now refuses to run until the user has a default workspace (PR
    #112 onboarding gate); tests covering the chat API should depend on
    this fixture so the gate doesn't 412 every request.  Tests that
    explicitly want the "no workspace yet" condition (workspace CRUD
    tests) skip this fixture.

    The workspace root lives under pytest's per-test ``tmp_path`` so
    pytest cleans it up automatically (fixes #275 — previously this
    fixture allocated via ``tempfile.mkdtemp`` and leaked directories
    every run).
    """
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    workspace = Workspace(
        id=uuid4(),
        user_id=test_user.id,
        name="Main",
        slug="main",
        path=str(workspace_root),
        is_default=True,
    )
    db_session.add(workspace)
    await db_session.commit()
    return workspace


@pytest.fixture
def app_with_overrides(db_session: AsyncSession, test_user: User) -> Generator[FastAPI]:
    """Create a FastAPI app with auth and database dependencies overridden."""
    app = create_app()

    async def override_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[current_active_user] = lambda: test_user

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
async def client(app_with_overrides: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Provide an async HTTP client for the overridden FastAPI app."""
    transport = ASGITransport(app=app_with_overrides)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
