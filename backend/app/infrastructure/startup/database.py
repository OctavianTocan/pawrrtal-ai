"""Startup hook: initialize database tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.database.legacy import create_db_and_tables
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=20)
async def start_database(app: FastAPI) -> None:
    """Create database tables for local/dev deployments."""
    del app
    await create_db_and_tables()
