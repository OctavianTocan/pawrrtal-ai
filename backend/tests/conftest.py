"""Shared backend test fixtures."""

import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app import models  # noqa: F401  # Registers ORM models on Base metadata.
from app.db import User, get_async_session
from app.db_base import Base
from app.models import Workspace
from app.users import current_active_user
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
async def db_session(test_user: User) -> AsyncGenerator[AsyncSession]:
    """Provide an isolated in-memory SQLite database session."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
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
