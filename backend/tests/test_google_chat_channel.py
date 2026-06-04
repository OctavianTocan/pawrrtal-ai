"""Tests for the Google Chat channel adapter.

Covers the three layers that carry logic:

- event decoding/extraction (``messages``): base64 Pub/Sub envelope →
  Chat event → field reads.
- delivery (``channel`` + ``delivery``): stream events → progressive
  ``update_message`` patches, verbose-gated (tools/thinking), with error
  and empty-turn fallbacks.
- identity (``dev_admin`` + ``crud``): dev-admin auto-link and the
  persistent per-user conversation.

Pure functions are tested directly; the DB paths mirror
``test_telegram_dev_admin.py`` (same ``db_session`` + seeded-admin shape).
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import ChannelMessage
from app.channels.crud import get_user_id_for_external
from app.channels.google_chat import delivery as delivery_module
from app.channels.google_chat.channel import (
    INITIAL_PLACEHOLDER_TEXT,
    SURFACE_GOOGLE_CHAT,
    GoogleChatChannel,
)
from app.channels.google_chat.commands import (
    COMMAND_MENU,
    CommandContext,
    dispatch_command,
)
from app.channels.google_chat.conversation import get_or_create_google_chat_conversation
from app.channels.google_chat.delivery import StreamingDelivery
from app.channels.google_chat.dev_admin import (
    GOOGLE_CHAT_PROVIDER,
    resolve_or_autolink_google_chat_user,
)
from app.channels.google_chat.messages import (
    decode_pubsub_message,
    event_type,
    message_text,
    parse_command,
    sender_display,
    sender_name,
    space_name,
    thread_name,
)
from app.channels.google_chat.settings import google_chat_settings
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User
from app.models import ChannelBinding, Conversation, Workspace
from app.providers.base import StreamEvent

pytestmark = pytest.mark.anyio

DEV_ADMIN_SENDER = "users/1234567890"
OTHER_SENDER = "users/9999999999"
_SPACE = "spaces/AAAA"
_THREAD = "spaces/AAAA/threads/TTTT"


def _chat_event(*, text: str = "hello", sender: str = DEV_ADMIN_SENDER) -> dict[str, Any]:
    """Build a representative Chat ``MESSAGE`` event."""
    return {
        "type": "MESSAGE",
        "space": {"name": _SPACE},
        "message": {
            "name": f"{_SPACE}/messages/MMMM",
            "text": text,
            "sender": {"name": sender, "displayName": "Tavi", "type": "HUMAN"},
            "thread": {"name": _THREAD},
        },
    }


def _pubsub_envelope(event: dict[str, Any], *, ack_id: str = "ack-1") -> dict[str, Any]:
    """Wrap a Chat event in the Pub/Sub ``receivedMessages`` shape."""
    data = base64.b64encode(json.dumps(event).encode("utf-8")).decode("ascii")
    return {"ackId": ack_id, "message": {"data": data}}


# ---------------------------------------------------------------------------
# messages — decode + field extraction
# ---------------------------------------------------------------------------


def test_decode_pubsub_message_decodes_message_event() -> None:
    ack_id, event = decode_pubsub_message(_pubsub_envelope(_chat_event()))
    assert ack_id == "ack-1"
    assert event is not None
    assert event_type(event) == "MESSAGE"


def test_decode_pubsub_message_rejects_bad_base64() -> None:
    bad = {"ackId": "ack-2", "message": {"data": "!!!not-base64!!!"}}
    ack_id, event = decode_pubsub_message(bad)
    assert ack_id == "ack-2"
    assert event is None


def test_decode_pubsub_message_handles_missing_data() -> None:
    ack_id, event = decode_pubsub_message({"ackId": "ack-3", "message": {}})
    assert ack_id == "ack-3"
    assert event is None


def test_event_extractors_read_message_fields() -> None:
    event = _chat_event(text="do the thing")
    assert message_text(event) == "do the thing"
    assert space_name(event) == _SPACE
    assert thread_name(event) == _THREAD
    assert sender_name(event) == DEV_ADMIN_SENDER
    assert sender_display(event) == "Tavi"


def _addon_event(*, text: str = "hello", sender: str = DEV_ADMIN_SENDER) -> dict[str, Any]:
    """Build a Google Workspace add-on ``MESSAGE`` event (the modern shape).

    Add-on Chat apps wrap the message under ``chat.messagePayload`` and omit
    the classic top-level ``type``/``message``/``space`` keys. This mirrors a
    real DM event captured from a live add-on Chat app.
    """
    sender_obj = {"name": sender, "displayName": "Tavi", "type": "HUMAN"}
    return {
        "commonEventObject": {"userLocale": "en", "hostApp": "CHAT"},
        "chat": {
            "user": sender_obj,
            "messagePayload": {
                "space": {"name": _SPACE, "type": "DM"},
                "message": {
                    "name": f"{_SPACE}/messages/MMMM",
                    "text": text,
                    "sender": sender_obj,
                    "thread": {"name": _THREAD},
                },
            },
        },
    }


def test_addon_event_type_is_message() -> None:
    # No top-level ``type``; the presence of ``messagePayload`` implies MESSAGE.
    assert event_type(_addon_event()) == "MESSAGE"


def test_addon_event_extractors_read_message_fields() -> None:
    event = _addon_event(text="add-on hi")
    assert message_text(event) == "add-on hi"
    assert space_name(event) == _SPACE
    assert thread_name(event) == _THREAD
    assert sender_name(event) == DEV_ADMIN_SENDER
    assert sender_display(event) == "Tavi"


def test_decode_pubsub_message_decodes_addon_event() -> None:
    ack_id, event = decode_pubsub_message(_pubsub_envelope(_addon_event()))
    assert ack_id == "ack-1"
    assert event is not None
    assert event_type(event) == "MESSAGE"
    assert message_text(event) == "hello"


def test_decode_pubsub_message_handles_url_safe_base64() -> None:
    # Live add-on payloads arrive URL-safe-encoded; the decoder must fall back
    # from the standard alphabet to the URL-safe one. The ">>>>" run forces
    # bytes that differ between the two alphabets so this genuinely exercises it.
    event = _addon_event(text="payload >>>>>>>> marker")
    url_safe = base64.urlsafe_b64encode(json.dumps(event).encode("utf-8")).decode("ascii")
    assert ("-" in url_safe) or ("_" in url_safe)
    ack_id, decoded = decode_pubsub_message({"ackId": "ack-u", "message": {"data": url_safe}})
    assert ack_id == "ack-u"
    assert decoded is not None
    assert message_text(decoded) == "payload >>>>>>>> marker"


# ---------------------------------------------------------------------------
# channel — streaming delivery (progressive patches)
# ---------------------------------------------------------------------------


async def _stream(events: list[StreamEvent]) -> AsyncIterator[StreamEvent]:
    for event in events:
        yield event


def _channel_message(message_name: str | None = "spaces/AAAA/messages/MMMM") -> ChannelMessage:
    return {
        "user_id": uuid4(),
        "conversation_id": uuid4(),
        "text": "hi",
        "surface": SURFACE_GOOGLE_CHAT,
        "model_id": "google-ai:google/gemini-3-flash-preview",
        "metadata": {"space_name": _SPACE, "thread_name": _THREAD, "message_name": message_name},
    }


def _patched_text(patch_mock: AsyncMock) -> str:
    """Return the ``text`` kwarg of the single ``update_message`` patch call."""
    call = patch_mock.await_args
    assert call is not None
    return str(call.kwargs["text"])


async def test_deliver_patches_placeholder_with_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    events: list[StreamEvent] = [
        {"type": "delta", "content": "Hello "},
        {"type": "delta", "content": "world"},
    ]
    async for _ in GoogleChatChannel().deliver(_stream(events), _channel_message()):
        pass

    patch_mock.assert_awaited()
    # ``_patched_text`` reads the LAST patch — the final render is the full answer.
    assert _patched_text(patch_mock) == "Hello world"


async def test_deliver_surfaces_error_with_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    events: list[StreamEvent] = [{"type": "error", "content": "boom"}]
    async for _ in GoogleChatChannel().deliver(_stream(events), _channel_message()):
        pass

    assert _patched_text(patch_mock).startswith("❌ ")


async def test_deliver_uses_fallback_for_empty_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    async for _ in GoogleChatChannel().deliver(_stream([]), _channel_message()):
        pass

    assert "without producing a reply" in _patched_text(patch_mock)


async def test_deliver_skips_patch_without_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery_module, "update_message", patch_mock)

    events: list[StreamEvent] = [{"type": "delta", "content": "ignored"}]
    async for _ in GoogleChatChannel().deliver(
        _stream(events), _channel_message(message_name=None)
    ):
        pass

    patch_mock.assert_not_awaited()


def test_initial_placeholder_text_is_nonempty() -> None:
    assert INITIAL_PLACEHOLDER_TEXT.strip()


async def _feed(delivery: StreamingDelivery, events: list[StreamEvent]) -> None:
    """Drive events through a delivery whose patch call is a no-op."""
    for event in events:
        await delivery.on_event(event)


async def test_streaming_shows_tools_at_verbose_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    delivery = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=1)
    await _feed(
        delivery,
        [
            {"type": "tool_use", "tool_use_id": "t1", "name": "web_search"},
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False},
            {"type": "delta", "content": "the answer"},
        ],
    )
    out = delivery.render(streaming=False)
    assert "web_search" in out
    assert "the answer" in out


async def test_streaming_hides_tools_at_verbose_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    delivery = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=0)
    await _feed(
        delivery,
        [
            {"type": "tool_use", "tool_use_id": "t1", "name": "web_search"},
            {"type": "delta", "content": "the answer"},
        ],
    )
    out = delivery.render(streaming=False)
    assert "web_search" not in out
    assert out == "the answer"


async def test_streaming_shows_thinking_only_at_verbose_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    events: list[StreamEvent] = [
        {"type": "thinking", "content": "let me think", "block_index": 0},
        {"type": "delta", "content": "answer"},
    ]
    quiet = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=1)
    await _feed(quiet, events)
    assert "let me think" not in quiet.render(streaming=False)

    loud = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=2)
    await _feed(loud, events)
    loud_out = loud.render(streaming=False)
    assert "let me think" in loud_out
    assert "answer" in loud_out


async def test_streaming_marks_failed_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery_module, "update_message", AsyncMock(return_value=True))
    delivery = StreamingDelivery(message_name="spaces/A/messages/M", verbose_level=1)
    await _feed(
        delivery,
        [
            {"type": "tool_use", "tool_use_id": "t1", "name": "broken_tool"},
            {"type": "tool_result", "tool_use_id": "t1", "content": "nope", "is_error": True},
            {"type": "delta", "content": "recovered"},
        ],
    )
    out = delivery.render(streaming=False)
    assert "broken_tool" in out
    assert "⚠️" in out


# ---------------------------------------------------------------------------
# commands — parse + dispatch
# ---------------------------------------------------------------------------


def _addon_command_event(*, command_text: str, argument_text: str | None = None) -> dict[str, Any]:
    """Build an add-on slash-command event (``chat.appCommandPayload``)."""
    message: dict[str, Any] = {"name": f"{_SPACE}/messages/CMD", "text": command_text}
    if argument_text is not None:
        message["argumentText"] = argument_text
    return {
        "commonEventObject": {"hostApp": "CHAT"},
        "chat": {
            "user": {"name": DEV_ADMIN_SENDER, "displayName": "Tavi"},
            "appCommandPayload": {"space": {"name": _SPACE}, "message": message},
        },
    }


def test_parse_command_from_plain_text() -> None:
    assert parse_command(_chat_event(text="/verbose 2")) == ("verbose", "2")


def test_parse_command_ignores_normal_message() -> None:
    assert parse_command(_chat_event(text="hello there")) is None


def test_parse_command_from_app_command_payload() -> None:
    event = _addon_command_event(command_text="/model gpt", argument_text="gpt")
    assert parse_command(event) == ("model", "gpt")


def test_parse_command_no_args() -> None:
    assert parse_command(_chat_event(text="/status")) == ("status", "")


@pytest.fixture
async def command_ctx(db_session: AsyncSession) -> CommandContext:
    """A CommandContext backed by a real user + google_chat conversation."""
    user = User(
        id=uuid4(),
        email=f"cmd-{uuid4()}@pawrrtal.dev",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    conversation = Conversation(
        id=uuid4(),
        user_id=user.id,
        title="Google Chat",
        origin_channel="google_chat",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return CommandContext(
        user_id=user.id,
        conversation=conversation,
        args="",
        sender_resource=DEV_ADMIN_SENDER,
        sender_email="cmd@pawrrtal.dev",
        session=db_session,
    )


async def test_command_help_lists_menu(command_ctx: CommandContext) -> None:
    reply = await dispatch_command(command="help", ctx=command_ctx)
    for name, _desc in COMMAND_MENU:
        assert f"/{name}" in reply


async def test_command_unknown(command_ctx: CommandContext) -> None:
    reply = await dispatch_command(command="frobnicate", ctx=command_ctx)
    assert "Unknown command" in reply


async def test_command_verbose_persists(command_ctx: CommandContext) -> None:
    command_ctx.args = "2"
    reply = await dispatch_command(command="verbose", ctx=command_ctx)
    assert "2" in reply
    assert command_ctx.conversation.verbose_level == 2


async def test_command_verbose_rejects_bad_value(command_ctx: CommandContext) -> None:
    command_ctx.args = "9"
    reply = await dispatch_command(command="verbose", ctx=command_ctx)
    assert "must be" in reply.lower()
    assert command_ctx.conversation.verbose_level is None


async def test_command_model_persists(command_ctx: CommandContext) -> None:
    command_ctx.args = "openai-codex:openai/gpt-5.5"
    reply = await dispatch_command(command="model", ctx=command_ctx)
    assert "openai-codex:openai/gpt-5.5" in reply
    assert command_ctx.conversation.model_id == "openai-codex:openai/gpt-5.5"


async def test_command_thinking_none_clears(command_ctx: CommandContext) -> None:
    command_ctx.conversation.reasoning_effort = "high"
    command_ctx.args = "none"
    await dispatch_command(command="thinking", ctx=command_ctx)
    assert command_ctx.conversation.reasoning_effort is None


async def test_command_thinking_rejects_bad_value(command_ctx: CommandContext) -> None:
    command_ctx.args = "ludicrous"
    reply = await dispatch_command(command="thinking", ctx=command_ctx)
    assert "Unknown level" in reply


async def test_command_status_reports_fields(command_ctx: CommandContext) -> None:
    reply = await dispatch_command(command="status", ctx=command_ctx)
    assert "Model" in reply
    assert "Verbosity" in reply


async def test_command_whoami_shows_identity(command_ctx: CommandContext) -> None:
    reply = await dispatch_command(command="whoami", ctx=command_ctx)
    assert DEV_ADMIN_SENDER in reply
    assert str(command_ctx.user_id) in reply


async def test_command_new_creates_fresh_conversation(
    command_ctx: CommandContext, db_session: AsyncSession
) -> None:
    await dispatch_command(command="new", ctx=command_ctx)
    rows = (
        (
            await db_session.execute(
                select(Conversation).where(
                    Conversation.user_id == command_ctx.user_id,
                    Conversation.origin_channel == "google_chat",
                )
            )
        )
        .scalars()
        .all()
    )
    # The fixture conversation plus the freshly started one.
    assert len(rows) >= 2


# ---------------------------------------------------------------------------
# dev_admin — single-user auto-link
# ---------------------------------------------------------------------------


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
        space_name=_SPACE,
        display="Tavi",
    )

    assert resolved == seeded_admin_user.id
    stmt = select(ChannelBinding).where(
        ChannelBinding.provider == GOOGLE_CHAT_PROVIDER,
        ChannelBinding.external_user_id == DEV_ADMIN_SENDER,
    )
    binding = (await db_session.execute(stmt)).scalar_one()
    assert binding.external_chat_id == _SPACE
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
        space_name=_SPACE,
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
        space_name=_SPACE,
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
        space_name=_SPACE,
        display="Tavi",
    )
    second = await resolve_or_autolink_google_chat_user(
        session=db_session,
        external_user_id=DEV_ADMIN_SENDER,
        space_name=_SPACE,
        display="Tavi",
    )

    assert first == second == seeded_admin_user.id
    bindings = (await db_session.execute(select(ChannelBinding))).scalars().all()
    assert len(bindings) == 1


# ---------------------------------------------------------------------------
# crud — persistent conversation
# ---------------------------------------------------------------------------


async def test_get_or_create_conversation_creates_then_reuses(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """First call creates a google_chat conversation; the second reuses it."""
    first = await get_or_create_google_chat_conversation(user_id=test_user.id, session=db_session)
    second = await get_or_create_google_chat_conversation(user_id=test_user.id, session=db_session)

    assert first.id == second.id
    assert first.origin_channel == "google_chat"
    rows = (
        (
            await db_session.execute(
                select(Conversation).where(Conversation.origin_channel == "google_chat")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_bound_sender_resolves_without_autolink(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """An existing binding resolves directly (no dev-admin config needed)."""
    db_session.add(
        ChannelBinding(
            user_id=test_user.id,
            provider=GOOGLE_CHAT_PROVIDER,
            external_user_id=OTHER_SENDER,
            external_chat_id=_SPACE,
            display_handle="someone",
            created_at=datetime.now(),
        )
    )
    await db_session.commit()

    resolved = await get_user_id_for_external(
        provider=GOOGLE_CHAT_PROVIDER,
        external_user_id=OTHER_SENDER,
        session=db_session,
    )
    assert resolved == test_user.id
