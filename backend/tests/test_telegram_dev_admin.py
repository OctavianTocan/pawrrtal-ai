"""Tests for the dev-admin Telegram auto-link helper.

Covers the four branches of ``resolve_or_autolink_telegram_user``:
unset env var, mismatched sender, missing admin user, and the happy
path where the binding is forged and the workspace ensured. The
integration test pipes a sender through ``handle_plain_message`` to
confirm the dev-admin gets a ``TelegramTurnContext`` (i.e. their
message routes to the LLM) instead of the onboarding nudge.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.channel import get_user_id_for_external, issue_link_code
from app.db import User
from app.integrations.telegram.dev_admin import (
    TELEGRAM_PROVIDER,
    resolve_or_autolink_telegram_user,
)
from app.integrations.telegram.handlers import (
    PROVIDER,
    TelegramTurnContext,
    handle_plain_message,
    handle_start_command,
)
from app.integrations.telegram.sender import TelegramSender
from app.models import ChannelBinding, Workspace

pytestmark = pytest.mark.anyio

DEV_ADMIN_TELEGRAM_ID = 5555555555
OTHER_TELEGRAM_ID = 9999999999


@pytest.fixture
def admin_user_email() -> str:
    """Email used by the seeded dev-admin in this test module."""
    return "dev-admin@pawrrtal-ai.dev"


@pytest.fixture
def admin_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``workspace_base_dir`` at the per-test ``tmp_path`` so the
    auto-link's call to ``ensure_dev_admin_workspace`` can seed a real
    filesystem directory without leaking outside the sandbox.
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


def _make_sender(telegram_id: int) -> TelegramSender:
    """Construct a ``TelegramSender`` for the given user_id (DM shape)."""
    return TelegramSender(
        user_id=telegram_id,
        chat_id=telegram_id,
        username="dev_admin_handle",
        full_name="Dev Admin",
    )


async def test_autolink_skipped_when_env_var_unset(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset ``TELEGRAM_DEV_ADMIN_ID`` → behaviour identical to the standard nudge."""
    monkeypatch.setattr(settings, "telegram_dev_admin_id", None)
    monkeypatch.setattr(settings, "admin_email", "dev-admin@pawrrtal-ai.dev")

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    result = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert result is None
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert bindings == []


async def test_autolink_skipped_when_sender_id_mismatch(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    seeded_admin_user: User,
) -> None:
    """Env var set, sender's Telegram ID does *not* match → no auto-bind."""
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    sender = _make_sender(OTHER_TELEGRAM_ID)
    result = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert result is None
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert bindings == []


async def test_autolink_skipped_when_admin_email_unset(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env var set but ``ADMIN_EMAIL`` empty → no auto-bind (logged, not raised)."""
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)
    monkeypatch.setattr(settings, "admin_email", None)

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    result = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert result is None
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert bindings == []


async def test_autolink_skipped_when_admin_user_missing(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ADMIN_EMAIL`` configured but no matching row → no auto-bind."""
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)
    monkeypatch.setattr(settings, "admin_email", "not-seeded@example.com")

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    result = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert result is None
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert bindings == []


async def test_autolink_happy_path_creates_binding_and_workspace(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    admin_workspace_root: Path,
    seeded_admin_user: User,
) -> None:
    """Configured env var + seeded admin user → binding forged, workspace ensured."""
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    result = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert result == seeded_admin_user.id

    stmt = select(ChannelBinding).where(
        ChannelBinding.provider == TELEGRAM_PROVIDER,
        ChannelBinding.external_user_id == str(DEV_ADMIN_TELEGRAM_ID),
    )
    binding = (await db_session.execute(stmt)).scalar_one()
    assert binding.user_id == seeded_admin_user.id
    assert binding.external_chat_id == str(DEV_ADMIN_TELEGRAM_ID)
    assert binding.display_handle == "dev_admin_handle"

    workspace_stmt = select(Workspace).where(Workspace.user_id == seeded_admin_user.id)
    workspace = (await db_session.execute(workspace_stmt)).scalar_one()
    assert workspace.is_default is True


async def test_autolink_returns_existing_binding_on_second_call(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    admin_workspace_root: Path,
    seeded_admin_user: User,
) -> None:
    """Second call reuses the binding without creating a duplicate row."""
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    first = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)
    second = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert first == seeded_admin_user.id
    assert second == seeded_admin_user.id

    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert len(bindings) == 1


async def test_autolink_does_not_override_existing_user_binding(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    seeded_admin_user: User,
) -> None:
    """If the Telegram ID is already bound to a *non-admin* user, the existing
    binding wins. Env-var-driven auto-link only fires on lookup miss.
    """
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    # Pre-existing binding pointing at the regular ``test_user``.
    code, _ = await issue_link_code(user_id=test_user.id, provider=PROVIDER, session=db_session)
    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    await handle_start_command(sender=sender, payload=code, session=db_session)

    resolved = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert resolved == test_user.id
    bound = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(DEV_ADMIN_TELEGRAM_ID),
        session=db_session,
    )
    assert bound == test_user.id


async def test_plain_message_from_dev_admin_routes_to_llm_pipeline(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    admin_workspace_root: Path,
    seeded_admin_user: User,
) -> None:
    """Integration: dev-admin's first plain message gets a routing context,
    not the unbound nudge.
    """
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    reply = await handle_plain_message(sender=sender, text="hello", session=db_session)

    assert isinstance(reply, TelegramTurnContext)
    assert reply.nexus_user_id == seeded_admin_user.id


async def test_empty_start_from_dev_admin_returns_connected_message(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    admin_workspace_root: Path,
    seeded_admin_user: User,
) -> None:
    """``/start`` with no code from the dev-admin Telegram ID auto-binds
    instead of showing the onboarding nudge.
    """
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    reply = await handle_start_command(sender=sender, payload=None, session=db_session)

    assert isinstance(reply, str)
    assert "Connected" in reply


async def test_empty_start_from_unknown_user_still_nudges(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-dev-admin sender sending bare ``/start`` still gets the nudge,
    even when the auto-link env var is set.
    """
    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    sender = _make_sender(OTHER_TELEGRAM_ID)
    reply = await handle_start_command(sender=sender, payload=None, session=db_session)

    assert isinstance(reply, str)
    assert "don't recognize" in reply.lower()


async def test_autolink_recovers_from_concurrent_insert_race(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    admin_workspace_root: Path,
    seeded_admin_user: User,
) -> None:
    """A commit-time ``IntegrityError`` from a concurrent winner is recovered:
    rollback, re-query, and return the winning user_id instead of crashing.

    Simulates the race window by patching ``get_user_id_for_external`` so
    the initial lookup misses (as it would for a true first-message race)
    while a competing binding already exists in the DB. The auto-link's
    own commit then trips the unique constraint and falls through to the
    recovery path's re-query, which surfaces the winner.
    """
    from app.crud import channel as channel_module

    monkeypatch.setattr(settings, "telegram_dev_admin_id", DEV_ADMIN_TELEGRAM_ID)

    # The "winner" of the race: another user that already owns the
    # Telegram ID's binding in the DB.
    winning_user_id = uuid4()
    winning_user = User(
        id=winning_user_id,
        email="winner@example.com",
        hashed_password="not-used",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(winning_user)
    db_session.add(
        ChannelBinding(
            user_id=winning_user_id,
            provider=TELEGRAM_PROVIDER,
            external_user_id=str(DEV_ADMIN_TELEGRAM_ID),
            external_chat_id=str(DEV_ADMIN_TELEGRAM_ID),
            display_handle="other_task",
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await db_session.commit()

    # Force a "lookup miss" on the entry path while leaving the
    # recovery-path lookup (which fires after rollback) untouched.
    original_lookup = channel_module.get_user_id_for_external
    miss_once = {"used": False}

    async def lookup_misses_then_recovers(
        *,
        provider: str,
        external_user_id: str,
        session: AsyncSession,
    ) -> uuid.UUID | None:
        if not miss_once["used"]:
            miss_once["used"] = True
            return None
        return await original_lookup(
            provider=provider,
            external_user_id=external_user_id,
            session=session,
        )

    monkeypatch.setattr(
        "app.integrations.telegram.dev_admin.get_user_id_for_external",
        lookup_misses_then_recovers,
    )

    sender = _make_sender(DEV_ADMIN_TELEGRAM_ID)
    resolved = await resolve_or_autolink_telegram_user(session=db_session, sender=sender)

    assert resolved == winning_user_id
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert len(bindings) == 1
    assert bindings[0].user_id == winning_user_id
