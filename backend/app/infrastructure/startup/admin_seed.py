"""Startup hook: seed the configured admin user."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.cli.admin_seed import seed_admin_user
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=30)
async def start_admin_seed(app: FastAPI) -> None:
    """Seed the admin user idempotently."""
    del app
    await seed_admin_user()
