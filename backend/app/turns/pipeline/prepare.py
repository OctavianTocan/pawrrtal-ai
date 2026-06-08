"""Turn Pipeline preparation for web/SSE chat turns."""

from __future__ import annotations

from app.agents.tool_surface import build_agent_tools
from app.channels import ChannelMessage, resolve_channel
from app.chat.cost_budget import enforce_cost_budget
from app.chat.external_mcp import load_external_mcp_configs
from app.plugins.adapters.turn_context import build_turn_context_providers
from app.providers.factory import resolve_llm
from app.providers.session_preparer import prepare_provider_session

from .types import ChatTurnInput, PreparedTurn, TurnCommand


async def prepare_turn(command: TurnCommand) -> PreparedTurn:
    """Resolve provider, tools, context providers, and session state for a turn."""
    if command.db_session is not None:
        await enforce_cost_budget(
            user_id=command.user_id,
            session=command.db_session,
            rid=command.request_id or "",
        )

    provider = resolve_llm(command.model_id, workspace_root=command.workspace_root)
    external_mcp_configs = (
        await load_external_mcp_configs(session=command.db_session, user_id=command.user_id)
        if command.db_session is not None
        else []
    )
    agent_tools = build_agent_tools(
        workspace_root=command.workspace_root,
        user_id=command.user_id,
        workspace_id=command.workspace_id,
        send_fn=command.send_fn,
        surface=command.surface,
        conversation_id=command.conversation_id,
        model_id=command.model_id,
        external_mcp_configs=external_mcp_configs,
    )
    provider_session = await prepare_provider_session(
        provider,
        conversation_id=command.conversation_id,
        workspace_root=command.workspace_root,
        model_id=command.model_id,
        tools=agent_tools,
        reasoning_effort=command.reasoning_effort,
        question=command.question,
    )
    channel_message: ChannelMessage = {
        "user_id": command.user_id,
        "conversation_id": command.conversation_id,
        "text": command.question,
        "surface": command.surface,
        "model_id": command.model_id,
        "metadata": command.metadata,
    }
    turn_input = ChatTurnInput(
        conversation_id=command.conversation_id,
        user_id=command.user_id,
        question=command.question,
        provider=provider,
        channel=resolve_channel(command.surface),
        channel_message=channel_message,
        workspace_root=command.workspace_root,
        tools=agent_tools,
        reasoning_effort=command.reasoning_effort,
        images=command.images,
        history_window=command.history_window,
        log_tag=command.log_tag,
        log_extras={
            "rid": command.request_id,
            "model_id": command.model_id,
            "surface": command.surface,
        },
        turn_context_providers=build_turn_context_providers(workspace_root=command.workspace_root),
        provider_session=provider_session,
    )
    return PreparedTurn(turn_input=turn_input, effective_model_id=command.model_id)
