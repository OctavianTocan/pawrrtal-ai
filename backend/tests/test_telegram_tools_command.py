"""Tests for the Telegram `/tools` command."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.types import AgentTool
from app.channels.telegram.bot import _TELEGRAM_COMMANDS
from app.channels.telegram.sender import TelegramSender
from app.channels.telegram.tools_command import handle_tools_command
from app.plugins.capability_catalog import CapabilityRecord


def test_telegram_command_menu_includes_tools() -> None:
    command_names = {command for command, _description in _TELEGRAM_COMMANDS}

    assert "tools" in command_names


@pytest.mark.anyio
async def test_tools_command_requires_binding() -> None:
    sender = TelegramSender(user_id=42, chat_id=42, username="tavi", full_name="Tavi")

    with patch(
        "app.channels.telegram.tools_command.resolve_or_autolink_telegram_user",
        new=AsyncMock(return_value=None),
    ):
        reply = await handle_tools_command(sender=sender, session=AsyncMock())

    assert "Connect your account first" in reply


@pytest.mark.anyio
async def test_tools_command_renders_actual_tools_and_plugin_capabilities(
    tmp_path: Path,
) -> None:
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    sender = TelegramSender(user_id=42, chat_id=42, username="tavi", full_name="Tavi")
    workspace = SimpleNamespace(id=workspace_id, path=str(tmp_path))
    conversation = SimpleNamespace(
        id=conversation_id,
        model_id="agy-api:google/gemini-3-flash-agent",
    )
    tool = AgentTool(
        name="search_plugin_capabilities",
        description="Search plugins.",
        parameters={"type": "object", "properties": {}},
        execute=AsyncMock(return_value="{}"),
    )
    capability = CapabilityRecord(
        plugin_id="notion",
        capability_id="notion_cli",
        type="cli_tool",
        title="Notion CLI",
        description="Run ntn.",
        tags=(),
        intents=("notion.workspace",),
        slots=("workspace_knowledge",),
        state="enabled",
        priority=0,
        exposure="direct_and_catalog",
        permissions=("secrets",),
        requires_confirmation=False,
        input_schema={},
        examples=(),
    )
    snapshot = SimpleNamespace(capabilities=(capability,))
    host = MagicMock()
    host.reload.return_value = (None, snapshot)

    with (
        patch(
            "app.channels.telegram.tools_command.resolve_or_autolink_telegram_user",
            new=AsyncMock(return_value=user_id),
        ),
        patch(
            "app.channels.telegram.tools_command.get_default_workspace",
            new=AsyncMock(return_value=workspace),
        ),
        patch(
            "app.channels.telegram.tools_command.get_or_create_telegram_conversation_full",
            new=AsyncMock(return_value=conversation),
        ),
        patch(
            "app.channels.telegram.tools_command.resolve_effective_model_id",
            new=MagicMock(return_value=conversation.model_id),
        ),
        patch(
            "app.channels.telegram.tools_command.compose_turn_tools",
            new=MagicMock(return_value=[tool]),
        ),
        patch("app.channels.telegram.tools_command.get_plugin_host", return_value=host),
    ):
        reply = await handle_tools_command(sender=sender, session=AsyncMock())

    assert "Tools available" in reply
    assert "agy-api:google/gemini-3-flash-agent" in reply
    assert "search_plugin_capabilities" in reply
    assert "workspace_knowledge" in reply
    assert "notion/notion_cli" in reply
