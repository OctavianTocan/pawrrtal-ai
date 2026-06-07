"""Google Chat channel — slash-command parse + dispatch (commands).

Covers ``parse_command`` (plain ``/cmd`` text + add-on ``appCommandPayload``)
and the command handlers, including the parity commands ``/stop`` and
``/config``. The picker-backed commands (``/thinking`` ``/verbose`` ``/model``)
and ``/lcm`` ``/compact`` live in the cards and lcm suites respectively.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.google_chat.commands import (
    COMMAND_MENU,
    CommandContext,
    apply_config_toggle,
    config_status_text,
    dispatch_command,
)
from app.channels.google_chat.messages import parse_command
from app.models import Conversation
from tests.channels.google_chat.helpers import DEV_ADMIN_SENDER, addon_command_event, chat_event

pytestmark = pytest.mark.anyio


def test_parse_command_from_plain_text() -> None:
    assert parse_command(chat_event(text="/verbose 2")) == ("verbose", "2")


def test_parse_command_ignores_normal_message() -> None:
    assert parse_command(chat_event(text="hello there")) is None


def test_parse_command_from_app_command_payload() -> None:
    event = addon_command_event(command_text="/model gpt", argument_text="gpt")
    assert parse_command(event) == ("model", "gpt")


def test_parse_command_from_app_command_id_without_slash_text() -> None:
    event = addon_command_event(command_text="", argument_text="openai/gpt-4o")
    event["chat"]["appCommandPayload"]["appCommandMetadata"] = {"appCommandId": "3"}
    assert parse_command(event) == ("model", "openai/gpt-4o")


def test_parse_command_no_args() -> None:
    assert parse_command(chat_event(text="/status")) == ("status", "")


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


async def test_command_model_rejects_unauthenticated_host(
    command_ctx: CommandContext,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.channels.google_chat.commands as commands_module

    command_ctx.workspace_root = tmp_path
    command_ctx.args = "agent-sdk:anthropic/claude-opus-4-7"
    monkeypatch.setattr(
        commands_module,
        "host_authenticated",
        lambda _host, *, workspace_root=None: False,
    )

    reply = await dispatch_command(command="model", ctx=command_ctx)

    assert "not available" in reply
    assert command_ctx.conversation.model_id is None


async def test_command_model_rejects_unknown_id(command_ctx: CommandContext) -> None:
    command_ctx.args = "not-a-real-model"
    reply = await dispatch_command(command="model", ctx=command_ctx)
    assert "Unknown model" in reply
    assert command_ctx.conversation.model_id is None


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


async def test_command_stop_explains_pull_model(command_ctx: CommandContext) -> None:
    reply = await dispatch_command(command="stop", ctx=command_ctx)
    assert "one message at a time" in reply.lower()


async def test_command_config_without_workspace(command_ctx: CommandContext) -> None:
    # The fixture user has no workspace, so /config reports that cleanly.
    reply = await dispatch_command(command="config", ctx=command_ctx)
    assert "workspace" in reply.lower()


def test_config_status_text_shows_defaults() -> None:
    text = config_status_text({})
    assert "Active Recall: on" in text
    assert "Search Workspace: off" in text


def test_config_toggle_round_trip(tmp_path: Path) -> None:
    reply = apply_config_toggle(tmp_path, {}, "active_recall off")
    assert "Active Recall set to off" in reply
    from app.infrastructure.keys import load_workspace_env

    assert load_workspace_env(tmp_path).get("ACTIVE_RECALL_ENABLED") == "false"


def test_config_toggle_rejects_bad_args(tmp_path: Path) -> None:
    assert "Usage" in apply_config_toggle(tmp_path, {}, "active_recall maybe")
