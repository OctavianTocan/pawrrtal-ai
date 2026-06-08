"""Startup hook: initialize database tables."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.infrastructure.config import settings
from app.infrastructure.database.legacy import create_db_and_tables
from app.infrastructure.database.safety import assert_database_target_safe
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI

_REPO_ROOT = Path(__file__).resolve().parents[4]


@startup_hook(order=20)
async def start_database(app: FastAPI) -> None:
    """Create database tables for local/dev deployments."""
    del app
    assert_database_target_safe(
        database_url=settings.database_url,
        sqlite_db_filename=settings.sqlite_db_filename,
        env=settings.env,
        repo_root=_REPO_ROOT,
    )
    await create_db_and_tables()
