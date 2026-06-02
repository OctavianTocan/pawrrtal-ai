"""Database CRUD helpers for Workspace rows.

These functions own the DB read/write side of workspace management.
Filesystem seeding lives in ``app.workspace.service`` (``seed_workspace``).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import settings
from app.workspace.service import seed_workspace

log = logging.getLogger(__name__)

# Stable folder name reserved for the seeded dev-admin user.  Using a fixed
# directory (instead of the random UUID layout the rest of the app uses)
# keeps the dev admin's workspace files in the same place across DB resets,
# so a developer can wipe Postgres without re-copying their working files.
DEV_ADMIN_WORKSPACE_DIRNAME = "dev-admin"

if TYPE_CHECKING:
    from app.models import UserPersonalization, Workspace


async def get_default_workspace(
    user_id: uuid.UUID,
    session: AsyncSession,
) -> Workspace | None:
    """Return the user's default workspace row, or None if it doesn't exist."""
    from app.models import Workspace  # noqa: PLC0415

    result = await session.execute(
        select(Workspace)
        .where(Workspace.user_id == user_id, Workspace.is_default.is_(True))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_workspaces(
    user_id: uuid.UUID,
    session: AsyncSession,
) -> list[Workspace]:
    """Return all workspaces owned by the user, default first."""
    from app.models import Workspace  # noqa: PLC0415

    result = await session.execute(
        select(Workspace)
        .where(Workspace.user_id == user_id)
        .order_by(Workspace.is_default.desc(), Workspace.created_at.asc())
    )
    return list(result.scalars().all())


async def create_workspace(
    user_id: uuid.UUID,
    session: AsyncSession,
    name: str = "Main",
    slug: str = "main",
    is_default: bool = True,
    personalization: UserPersonalization | None = None,
    *,
    path: Path | None = None,
) -> Workspace:
    """Create a new workspace row in the DB and seed its directory.

    Does NOT commit — the caller is responsible for committing the session so
    this can participate in larger transactions.

    Pass ``path`` to pin the workspace directory to a caller-supplied
    location instead of the default ``{workspace_base_dir}/{uuid}`` layout.
    Reserved for the dev-admin stable-folder flow.
    """
    from app.models import Workspace  # noqa: PLC0415

    workspace_id = uuid.uuid4()

    # Seed filesystem first so we can capture the canonical path.
    root = seed_workspace(workspace_id, personalization, path=path)

    ws = Workspace(
        id=workspace_id,
        user_id=user_id,
        name=name,
        slug=slug,
        path=str(root),
        is_default=is_default,
        created_at=datetime.now(UTC),
    )
    session.add(ws)

    return ws


async def ensure_default_workspace(
    user_id: uuid.UUID,
    session: AsyncSession,
    personalization: UserPersonalization | None = None,
) -> Workspace:
    """Return the existing default workspace or create one.

    Safe to call multiple times — idempotent against both normal duplicate
    calls and the React StrictMode double-effect pattern.

    Strategy:
    1. Fast-path: look up an existing default workspace and return it.
    2. Slow-path: create one.  If two concurrent requests both pass step 1
       before either has committed, the partial unique index
       ``uq_workspaces_one_default_per_user`` makes the second INSERT raise
       an ``IntegrityError``.  We catch that, roll back the failed nested
       savepoint, and re-fetch — which now finds the row the first request
       committed.
    """
    existing = await get_default_workspace(user_id, session)
    if existing is not None:
        return existing

    orphaned_path: Path | None = None
    try:
        # Use a savepoint so a constraint violation only rolls back this
        # nested transaction, not the whole outer session.
        async with session.begin_nested():
            ws = await create_workspace(
                user_id=user_id,
                session=session,
                name="Main",
                slug="main",
                is_default=True,
                personalization=personalization,
            )
            orphaned_path = Path(ws.path)
        return ws
    except IntegrityError:
        # Another concurrent request already inserted the default workspace.
        # The savepoint was rolled back automatically; re-fetch the winner.
        if orphaned_path is not None:
            await _remove_orphan_workspace_dir(orphaned_path)
        log.warning(
            "ensure_default_workspace: IntegrityError for user %s — "
            "concurrent insert detected, re-fetching existing row.",
            user_id,
        )
        result = await get_default_workspace(user_id, session)
        if result is None:
            # Should never happen: the constraint fired but no row exists.
            raise RuntimeError(
                f"ensure_default_workspace: could not find default workspace "
                f"for user {user_id} after IntegrityError"
            ) from None
        return result


async def ensure_dev_admin_workspace(
    user_id: uuid.UUID,
    session: AsyncSession,
    personalization: UserPersonalization | None = None,
) -> Workspace:
    """Return the dev admin's default workspace, creating it at a stable path.

    Mirrors :func:`ensure_default_workspace` but pins the on-disk directory
    to ``{workspace_base_dir}/dev-admin`` so the folder survives DB resets.
    Filesystem seeding is idempotent — :func:`seed_workspace` only writes
    files and directories that do not already exist, so a developer's
    working files in ``dev-admin/`` are preserved when the DB row is
    recreated.

    Reserved for the dev-login endpoint (which is itself gated to non-prod);
    real users should keep going through :func:`ensure_default_workspace`.
    """
    existing = await get_default_workspace(user_id, session)
    if existing is not None:
        if existing.path is not None:
            seed_workspace(existing.id, personalization, path=Path(existing.path))
        return existing

    stable_path = Path(settings.workspace_base_dir) / DEV_ADMIN_WORKSPACE_DIRNAME
    try:
        async with session.begin_nested():
            ws = await create_workspace(
                user_id=user_id,
                session=session,
                name="Main",
                slug="main",
                is_default=True,
                personalization=personalization,
                path=stable_path,
            )
        return ws
    except IntegrityError:
        # Same concurrent-insert recovery as ensure_default_workspace; the
        # stable directory is left in place because the winning row points
        # at it too.
        log.warning(
            "ensure_dev_admin_workspace: IntegrityError for user %s — "
            "concurrent insert detected, re-fetching existing row.",
            user_id,
        )
        result = await get_default_workspace(user_id, session)
        if result is None:
            raise RuntimeError(
                f"ensure_dev_admin_workspace: could not find default workspace "
                f"for user {user_id} after IntegrityError"
            ) from None
        return result


async def update_workspace(
    session: AsyncSession,
    workspace: Workspace,
    *,
    name: str | None = None,
    slug: str | None = None,
    path: str | None = None,
    is_default: bool | None = None,
) -> Workspace:
    """Patch a workspace row.

    Only keys with a non-None value are applied — callers pass the resolved
    subset of ``WorkspaceUpdate`` they want to write.  When ``is_default``
    flips to ``True`` we first demote the user's existing default in the
    same session so the partial unique index
    ``uq_workspaces_one_default_per_user`` stays satisfied.

    Does NOT commit — the caller participates in the outer transaction.
    """
    if name is not None:
        workspace.name = name
    if slug is not None:
        workspace.slug = slug
    if path is not None:
        workspace.path = path
    if is_default is True and not workspace.is_default:
        # Demote any existing default workspace for this user before promoting
        # the new one — the partial unique index only permits a single
        # is_default=True row per user.
        existing_default = await get_default_workspace(workspace.user_id, session)
        if existing_default is not None and existing_default.id != workspace.id:
            existing_default.is_default = False
            await session.flush()
        workspace.is_default = True

    return workspace


async def delete_workspace(
    session: AsyncSession,
    workspace: Workspace,
) -> None:
    """Delete a workspace row from the database.

    Filesystem cleanup is intentionally out of scope here — workspaces own
    user files that we don't want to silently wipe on a stray DELETE.
    Operators reclaim disk space manually.
    """
    await session.delete(workspace)


async def _remove_orphan_workspace_dir(path: Path) -> None:
    """Remove a just-seeded workspace directory after its DB row rolled back."""
    resolved = _validated_orphan_workspace_dir(path)
    if resolved is None:
        return

    try:
        await asyncio.to_thread(shutil.rmtree, resolved)
    except FileNotFoundError:
        return
    except OSError:
        log.warning("Failed to remove orphan workspace directory: %s", resolved, exc_info=True)


def _validated_orphan_workspace_dir(path: Path) -> Path | None:
    """Return a safe workspace path to delete, or None when it is unsafe."""
    try:
        workspace_base = Path(settings.workspace_base_dir).resolve()
        resolved = path.resolve()
        resolved.relative_to(workspace_base)
    except ValueError:
        log.warning("Refusing to remove workspace path outside base dir: %s", path)
        return None
    except OSError:
        log.warning("Could not resolve orphan workspace path: %s", path, exc_info=True)
        return None
    return resolved
