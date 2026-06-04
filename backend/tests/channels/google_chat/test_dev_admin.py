"""Google Chat channel — single-user dev-admin auto-link (dev_admin).

A configured ``GOOGLE_CHAT_DEV_ADMIN_ID`` matching the seeded admin forges a
``ChannelBinding`` (and ensures a default workspace); a mismatched or unset
sender gets no binding; a second call reuses the binding rather than
duplicating it.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.google_chat.dev_admin import (
    GOOGLE_CHAT_PROVIDER,
    resolve_or_autolink_google_chat_user,
)
from app.channels.google_chat.settings import google_chat_settings
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User
from app.models import ChannelBinding, Workspace
from tests.channels.google_chat.helpers import DEV_ADMIN_SENDER, OTHER_SENDER, SPACE

pytestmark = pytest.mark.anyio


@pytest.fixture
def admin_user_email() -> str:
    """Email used by the seeded dev-admin in this test module."""
    return "dev-admin@pawrrtal-ai.dev"


@pytest.fixture
def admin_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``workspace_base_dir`` at ``tmp_path`` so the auto-link's
    ``ensure_dev_admin_workspace`` seeds a directory inside the sandbox.
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
async def seeded_admin_user(
    db_session: AsyncSession,
    admin_user_email: str,
    monkeypatch: pytest.MonkeyPatch,
) -> User:
    """Insert a row matching ``settings.admin_email`` and return it."""
    monkeypatch.setattr(settings, "admin_email", admin_user_email)
    admin = User(
        id=uuid4(),
        email=admin_user_email,
        hashed_password="not-used",
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def test_autolink_binds_configured_sender(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    admin_workspace_root: Path,
    seeded_admin_user: User,
) -> None:
    """Configured sender + seeded admin → binding forged, workspace ensured."""
    monkeypatch.setattr(google_chat_settings, "google_chat_dev_admin_id", DEV_ADMIN_SENDER)

    resolved = await resolve_or_autolink_google_chat_user(
        session=db_session,
        external_user_id=DEV_ADMIN_SENDER,
        space_name=SPACE,
        display="Tavi",
    )

    assert resolved == seeded_admin_user.id
    stmt = select(ChannelBinding).where(
        ChannelBinding.provider == GOOGLE_CHAT_PROVIDER,
        ChannelBinding.external_user_id == DEV_ADMIN_SENDER,
    )
    binding = (await db_session.execute(stmt)).scalar_one()
    assert binding.external_chat_id == SPACE
    workspace = (
        await db_session.execute(select(Workspace).where(Workspace.user_id == seeded_admin_user.id))
    ).scalar_one()
    assert workspace.is_default is True


async def test_autolink_skipped_on_sender_mismatch(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    seeded_admin_user: User,
) -> None:
    """A sender that isn't the configured dev-admin gets no binding."""
    monkeypatch.setattr(google_chat_settings, "google_chat_dev_admin_id", DEV_ADMIN_SENDER)

    resolved = await resolve_or_autolink_google_chat_user(
        session=db_session,
        external_user_id=OTHER_SENDER,
        space_name=SPACE,
        display=None,
    )

    assert resolved is None
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert bindings == []


async def test_autolink_skipped_when_unset(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset ``GOOGLE_CHAT_DEV_ADMIN_ID`` → no auto-bind."""
    monkeypatch.setattr(google_chat_settings, "google_chat_dev_admin_id", "")

    resolved = await resolve_or_autolink_google_chat_user(
        session=db_session,
        external_user_id=DEV_ADMIN_SENDER,
        space_name=SPACE,
        display=None,
    )

    assert resolved is None


async def test_autolink_returns_existing_binding(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    admin_workspace_root: Path,
    seeded_admin_user: User,
) -> None:
    """A second call reuses the binding without creating a duplicate row."""
    monkeypatch.setattr(google_chat_settings, "google_chat_dev_admin_id", DEV_ADMIN_SENDER)

    first = await resolve_or_autolink_google_chat_user(
        session=db_session,
        external_user_id=DEV_ADMIN_SENDER,
        space_name=SPACE,
        display="Tavi",
    )
    second = await resolve_or_autolink_google_chat_user(
        session=db_session,
        external_user_id=DEV_ADMIN_SENDER,
        space_name=SPACE,
        display="Tavi",
    )

    assert first == second == seeded_admin_user.id
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert len(bindings) == 1
