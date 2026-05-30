"""Startup hook: migrate legacy user-keyed workspace env files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.cli.migrate_workspace_env import migrate_user_keyed_env_files_for_all_users
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=40)
async def start_workspace_env_migration(app: FastAPI) -> None:
    """Run the idempotent workspace env migration."""
    del app
    await migrate_user_keyed_env_files_for_all_users()
