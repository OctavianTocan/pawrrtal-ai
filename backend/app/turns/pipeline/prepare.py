"""Turn Pipeline preparation for web/SSE chat turns."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.agents.tool_surface import build_agent_tools
from app.agents.types import AgentTool
from app.channels import ChannelMessage, resolve_channel
from app.chat.cost_budget import enforce_cost_budget
from app.chat.external_mcp import load_external_mcp_configs
from app.plugins.adapters.turn_context import (
    TurnContextProviderAdapter,
    build_turn_context_providers,
)
from app.providers.selection import require_provider
from app.providers.session_preparer import prepare_provider_session
from app.tools.send_message import SendFn

from .types import ChatTurnInput, PreparedTurn, TurnCommand


async def prepare_turn(command: TurnCommand) -> PreparedTurn:
    """Resolve provider, tools, context providers, and session state for a turn."""
    if command.db_session is not None:
        await enforce_cost_budget(
            user_id=command.user_id,
            session=command.db_session,
            rid=command.request_id or "",
        )

    selection = command.provider_selection or require_provider(
        command.model_id,
        workspace_root=command.workspace_root,
    )
    external_mcp_configs = (
        await load_external_mcp_configs(session=command.db_session, user_id=command.user_id)
        if command.db_session is not None
        else []
    )
    agent_tools = compose_turn_tools(
        workspace_root=command.workspace_root,
        user_id=command.user_id,
        workspace_id=command.workspace_id,
        send_fn=command.send_fn,
        surface=command.surface,
        conversation_id=command.conversation_id,
        model_id=selection.effective_model_id,
        external_mcp_configs=external_mcp_configs,
    )
    provider_session = await prepare_provider_session(
        selection.provider,
        conversation_id=command.conversation_id,
        workspace_root=command.workspace_root,
        model_id=selection.effective_model_id,
        tools=agent_tools,
        reasoning_effort=command.reasoning_effort,
        question=command.question,
    )
    channel_message: ChannelMessage = {
        "user_id": command.user_id,
        "conversation_id": command.conversation_id,
        "text": command.channel_text or command.question,
        "surface": command.surface,
        "model_id": selection.effective_model_id,
        "metadata": command.channel_metadata,
    }
    turn_input = ChatTurnInput(
        conversation_id=command.conversation_id,
        user_id=command.user_id,
        question=command.question,
        provider=selection.provider,
        channel=command.delivery_adapter or resolve_channel(command.surface),
        channel_message=channel_message,
        workspace_root=command.workspace_root,
        tools=agent_tools,
        reasoning_effort=command.reasoning_effort,
        images=command.images,
        history_window=command.history_window,
        log_tag=command.log_tag,
        log_extras={
            "rid": command.request_id,
            "model_id": selection.effective_model_id,
            "surface": command.surface,
        },
        verbose_level=command.verbose_level,
        turn_context_providers=_turn_context_providers(command),
        provider_session=provider_session,
        draft_updater=command.draft_updater,
        on_turn_context_finished=command.on_turn_context_finished,
    )
    return PreparedTurn(turn_input=turn_input, effective_model_id=selection.effective_model_id)


def compose_turn_tools(
    *,
    workspace_root: Path | None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    send_fn: SendFn | None = None,
    surface: str | None = None,
    conversation_id: uuid.UUID | None = None,
    model_id: str | None = None,
    external_mcp_configs: list[dict[str, Any]] | None = None,
) -> list[AgentTool]:
    """Compose the agent tool surface when a workspace is available."""
    if workspace_root is None or workspace_id is None:
        return []
    return build_agent_tools(
        workspace_root=workspace_root,
        user_id=user_id,
        workspace_id=workspace_id,
        send_fn=send_fn,
        surface=surface,
        conversation_id=conversation_id,
        model_id=model_id,
        external_mcp_configs=external_mcp_configs,
    )


def _turn_context_providers(command: TurnCommand) -> list[TurnContextProviderAdapter]:
    """Build turn context providers only when the turn has a workspace root."""
    if command.workspace_root is None:
        return []
    return build_turn_context_providers(workspace_root=command.workspace_root)
