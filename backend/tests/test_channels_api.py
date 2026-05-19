"""Channels API + binding lifecycle tests.

Exercises the /api/v1/channels routes plus the underlying
issue/redeem/unbind helpers. Avoids spinning up the real Telegram bot
by going through the framework-thin handlers in
``app.integrations.telegram.handlers``.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.channel import (
    delete_binding,
    get_user_id_for_external,
    issue_link_code,
    list_bindings,
)
from app.db import User
from app.integrations.telegram.handlers import (
    PROVIDER,
    handle_plain_message,
    handle_start_command,
)
from app.integrations.telegram.sender import TelegramSender

pytestmark = pytest.mark.anyio


@pytest.fixture
def telegram_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the deployment has a usable Telegram bot configured."""
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(settings, "telegram_bot_username", "pawrrtal_test_bot")


async def test_link_returns_503_when_telegram_unconfigured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frontend gets a clean disabled-state signal when no token is set."""
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_bot_username", "")

    response = await client.post("/api/v1/channels/telegram/link")

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


async def test_link_issues_code_with_deep_link(
    client: AsyncClient,
    telegram_configured: None,
) -> None:
    """The link endpoint returns plaintext code + deep link, exactly once."""
    response = await client.post("/api/v1/channels/telegram/link")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["code"]
    assert body["bot_username"] == "pawrrtal_test_bot"
    assert body["deep_link"] == (f"https://t.me/pawrrtal_test_bot?start={body['code']}")
    assert "expires_at" in body


async def test_list_channels_starts_empty(client: AsyncClient) -> None:
    """A user without bindings sees an empty list (never null)."""
    response = await client.get("/api/v1/channels")
    assert response.status_code == 200
    assert response.json() == []


async def test_unlink_is_idempotent(client: AsyncClient) -> None:
    """DELETE on a non-existent binding still returns 204 so the UI can fire-and-forget."""
    response = await client.delete("/api/v1/channels/telegram/link")
    assert response.status_code == 204


async def test_redeem_via_start_handler_creates_binding(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """End-to-end: issue a code, redeem it via /start, see the binding land."""
    code, _ = await issue_link_code(
        user_id=test_user.id,
        provider=PROVIDER,
        session=db_session,
    )

    sender = TelegramSender(
        user_id=987654321,
        chat_id=987654321,
        username="tavi_test",
        full_name="Tavi Test",
    )
    reply = await handle_start_command(sender=sender, payload=code, session=db_session)
    assert "Connected" in reply

    bound_user = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=db_session,
    )
    assert bound_user == test_user.id

    bindings = await list_bindings(user_id=test_user.id, session=db_session)
    assert len(bindings) == 1
    assert bindings[0].external_chat_id == "987654321"
    assert bindings[0].display_handle == "tavi_test"


async def test_redeem_rejects_replay(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """A code can be redeemed at most once, even if the same Telegram user retries."""
    code, _ = await issue_link_code(
        user_id=test_user.id,
        provider=PROVIDER,
        session=db_session,
    )
    sender = TelegramSender(user_id=42, chat_id=42, username=None, full_name=None)

    first = await handle_start_command(sender=sender, payload=code, session=db_session)
    assert "Connected" in first

    second = await handle_start_command(sender=sender, payload=code, session=db_session)
    assert "didn't work" in second.lower()


async def test_plain_message_nudges_unknown_users(
    db_session: AsyncSession,
) -> None:
    """A Telegram user with no binding gets the onboarding nudge, not a chat reply."""
    sender = TelegramSender(user_id=111, chat_id=111, username=None, full_name=None)
    reply = await handle_plain_message(sender=sender, text="hello", session=db_session)
    assert isinstance(reply, str)
    assert "don't recognize" in reply.lower()


async def test_plain_message_acks_bound_users(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """A bound user's message returns a TelegramTurnContext for LLM routing."""
    code, _ = await issue_link_code(user_id=test_user.id, provider=PROVIDER, session=db_session)
    sender = TelegramSender(user_id=222, chat_id=222, username="bound", full_name=None)
    await handle_start_command(sender=sender, payload=code, session=db_session)

    reply = await handle_plain_message(sender=sender, text="how's it going", session=db_session)
    # Bound users no longer get a string ack — they get a routing context
    # the bot dispatcher hands to the LLM pipeline.
    assert not isinstance(reply, str)
    assert reply.pawrrtal_user_id == test_user.id


async def test_unbind_removes_binding(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """delete_binding wipes the row so the next message gets the nudge again."""
    code, _ = await issue_link_code(user_id=test_user.id, provider=PROVIDER, session=db_session)
    sender = TelegramSender(user_id=333, chat_id=333, username=None, full_name=None)
    await handle_start_command(sender=sender, payload=code, session=db_session)

    deleted = await delete_binding(user_id=test_user.id, provider=PROVIDER, session=db_session)
    assert deleted is True

    reply = await handle_plain_message(sender=sender, text="still here?", session=db_session)
    assert isinstance(reply, str)
    assert "don't recognize" in reply.lower()
