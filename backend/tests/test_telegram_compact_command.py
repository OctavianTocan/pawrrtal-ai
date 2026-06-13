"""Tests for the Telegram ``/compact`` command handler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.channels.telegram.compact_command import handle_compact_command


def _sender(*, user_id: int = 42, thread_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, chat_id=user_id, thread_id=thread_id)


@pytest.mark.anyio
async def test_returns_disabled_message_when_lcm_off() -> None:
    """When ``settings.lcm_enabled`` is False the handler short-circuits."""
    fake_settings = SimpleNamespace(
        lcm_enabled=False, lcm_fresh_tail_count=64, lcm_leaf_chunk_tokens=20_000
    )
    with patch("app.channels.telegram.compact_command.settings", fake_settings):
        reply = await handle_compact_command(sender=_sender(), session=AsyncMock())
    assert "LCM is disabled" in reply


@pytest.mark.anyio
async def test_returns_not_bound_when_no_user_binding() -> None:
    """Telegram users that haven't redeemed a link code get a clear ask."""
    fake_settings = SimpleNamespace(
        lcm_enabled=True, lcm_fresh_tail_count=64, lcm_leaf_chunk_tokens=20_000
    )
    with (
        patch("app.channels.telegram.compact_command.settings", fake_settings),
        patch(
            "app.channels.telegram.compact_command.get_user_id_for_external",
            AsyncMock(return_value=None),
        ),
    ):
        reply = await handle_compact_command(sender=_sender(), session=AsyncMock())
    assert "Connect your account" in reply


@pytest.mark.anyio
async def test_returns_nothing_to_compact_when_compactor_returns_false() -> None:
    """``compact_leaf_if_needed`` returns False when the threshold isn't crossed."""
    import uuid as uuid_mod

    fake_user = uuid_mod.uuid4()
    fake_conversation = SimpleNamespace(id=uuid_mod.uuid4(), model_id=None)
    fake_settings = SimpleNamespace(
        lcm_enabled=True, lcm_fresh_tail_count=64, lcm_leaf_chunk_tokens=20_000
    )

    def _noop_lock(_id: uuid_mod.UUID) -> _NoopLockCM:
        return _NoopLockCM()

    with (
        patch("app.channels.telegram.compact_command.settings", fake_settings),
        patch(
            "app.channels.telegram.compact_command.get_user_id_for_external",
            AsyncMock(return_value=fake_user),
        ),
        patch(
            "app.channels.telegram.compact_command.get_or_create_telegram_conversation_full",
            AsyncMock(return_value=fake_conversation),
        ),
        patch(
            "app.channels.telegram.compact_command.resolve_effective_model_id",
            Mock(return_value="claude-code-pty:anthropic/claude-sonnet-4-6"),
        ),
        patch(
            "app.channels.telegram.compact_command.compact_leaf_if_needed",
            AsyncMock(return_value=False),
        ),
        patch("app.channels.telegram.compact_command.acquire_lcm_lock", _noop_lock),
        patch(
            "app.channels.telegram.compact_command.async_session_maker",
            return_value=_AsyncSessionCM(),
        ),
    ):
        reply = await handle_compact_command(sender=_sender(), session=AsyncMock())

    assert "Nothing to compact" in reply
    assert "64" in reply  # fresh_tail_count surfaces in the message


@pytest.mark.anyio
async def test_returns_compacted_message_on_success() -> None:
    """Successful compaction yields the success line, no error class."""
    import uuid as uuid_mod

    fake_user = uuid_mod.uuid4()
    fake_conversation = SimpleNamespace(
        id=uuid_mod.uuid4(), model_id="claude-code-pty:anthropic/claude-opus-4-7"
    )
    fake_settings = SimpleNamespace(
        lcm_enabled=True, lcm_fresh_tail_count=64, lcm_leaf_chunk_tokens=20_000
    )

    def _noop_lock(_id: uuid_mod.UUID) -> _NoopLockCM:
        return _NoopLockCM()

    with (
        patch("app.channels.telegram.compact_command.settings", fake_settings),
        patch(
            "app.channels.telegram.compact_command.get_user_id_for_external",
            AsyncMock(return_value=fake_user),
        ),
        patch(
            "app.channels.telegram.compact_command.get_or_create_telegram_conversation_full",
            AsyncMock(return_value=fake_conversation),
        ),
        patch(
            "app.channels.telegram.compact_command.resolve_effective_model_id",
            Mock(return_value="claude-code-pty:anthropic/claude-sonnet-4-6"),
        ),
        patch(
            "app.channels.telegram.compact_command.compact_leaf_if_needed",
            AsyncMock(return_value=True),
        ),
        patch("app.channels.telegram.compact_command.acquire_lcm_lock", _noop_lock),
        patch(
            "app.channels.telegram.compact_command.async_session_maker",
            return_value=_AsyncSessionCM(),
        ),
    ):
        reply = await handle_compact_command(sender=_sender(), session=AsyncMock())

    assert "Compacted" in reply
    assert "failed" not in reply.lower()


class _AsyncSessionCM:
    """Minimal async-context-manager stand-in for ``async_session_maker()``."""

    async def __aenter__(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _NoopLockCM:
    """No-op stand-in for :func:`acquire_lcm_lock` — yields control immediately."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> bool:
        return False
