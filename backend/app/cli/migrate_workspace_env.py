"""One-time migration from user-keyed to workspace-keyed env files.

Before the workspace-keying migration (ADR
``2026-05-15-plugin-system-and-notion-integration``), encrypted ``.env``
files lived at ``{workspace_base_dir}/{user_id}/.env``.  The new layout
keys them by workspace, at ``{workspace_base_dir}/{workspace_id}/.env``,
so each of a user's workspaces gets its own credentials slate.

This module walks the user table at startup and migrates each user's
legacy file into their default workspace's path.  Users without a
default workspace are skipped (they haven't completed onboarding yet,
so the file shouldn't exist).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.legacy import async_session_maker
from app.infrastructure.keys import migrate_user_keyed_env_file
from app.models import Workspace

logger = logging.getLogger(__name__)


async def _migrate_one_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    default_workspace_id: uuid.UUID,
) -> bool:
    """Migrate one user's legacy env file; return ``True`` if a file moved.

    Logs and swallows ``OSError`` so a single filesystem failure doesn't
    abort the migration for everyone else; emits a WARN if the user has
    more than one workspace so the operator knows the secondary
    workspaces will start with an empty credentials slate.
    """
    try:
        moved = migrate_user_keyed_env_file(
            user_id=user_id,
            default_workspace_id=default_workspace_id,
        )
    except OSError as err:
        # A repeat startup will retry whichever users were missed.
        logger.warning(
            "workspace_env_migration: failed for user_id=%s: %s",
            user_id,
            err,
        )
        return False

    if moved:
        workspace_count = await session.scalar(
            select(func.count()).select_from(Workspace).where(Workspace.user_id == user_id)
        )
        if workspace_count and workspace_count > 1:
            logger.warning(
                "workspace_env_migration: user_id=%s has %d workspaces; "
                "only default_workspace_id=%s inherited legacy keys "
                "(secondary workspaces start with an empty .env)",
                user_id,
                workspace_count,
                default_workspace_id,
            )
    return moved


async def migrate_user_keyed_env_files_for_all_users() -> int:
    """Migrate every user's legacy env file into their default workspace.

    Returns the count of files migrated this run (zero on a clean
    startup where no legacy files remain).

    The function is idempotent: subsequent calls do nothing because the
    legacy source files have been renamed with a ``.migrated-<ts>``
    suffix on the first successful run.
    """
    migrated = 0
    async with async_session_maker() as session:
        # Pulling the default workspaces directly avoids a separate
        # "list users, then look up their workspace" two-step. We don't
        # care about users who never created a workspace — their legacy
        # files (if any) stay quarantined for manual recovery.
        result = await session.execute(
            select(Workspace.id, Workspace.user_id).where(Workspace.is_default.is_(True))
        )
        for workspace_id, user_id in result.all():
            if await _migrate_one_user(
                session,
                user_id=user_id,
                default_workspace_id=workspace_id,
            ):
                migrated += 1

    if migrated:
        logger.info(
            "workspace_env_migration: migrated %d legacy file(s) this startup",
            migrated,
        )
    return migrated
