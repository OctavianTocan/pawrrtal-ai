"""Dependencies for the EventBus, injected from the API layer down into core.

These functions encapsulate persistence side-effects that the EventBus
handlers need, without creating core -> crud layer violations.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from app.core.agent_loop.tools import build_agent_tools
from app.core.agent_loop.types import (
    PermissionCheckFn,
    PermissionCheckResult,
)
from app.core.governance.permissions import (
    PermissionContext,
    build_default_permission_check,
)
from app.core.governance.workspace_context import load_workspace_context
from app.core.providers import default_model, resolve_llm
from app.crud.chat_message import (
    append_assistant_placeholder,
    finalize_assistant_message,
)
from app.crud.workspace import get_default_workspace
from app.db import async_session_maker

logger = logging.getLogger(__name__)


async def run_agent_turn(prompt: str, user_id: uuid.UUID) -> str:
    """Stream one provider turn and return the concatenated assistant text.

    Resolves the catalog default model + the user's workspace + the
    standard tool composition.  Skips workspace tools when the user
    hasn't completed onboarding (no default workspace) — webhook /
    scheduled traffic shouldn't be gated on the onboarding flow.
    """
    async with async_session_maker() as session:
        workspace = await get_default_workspace(user_id, session)

    workspace_root: Path | None = Path(workspace.path) if workspace is not None else None
    workspace_ctx = load_workspace_context(workspace_root) if workspace_root is not None else None
    system_prompt = workspace_ctx.system_prompt if workspace_ctx is not None else None
    enabled_tools = workspace_ctx.enabled_tools if workspace_ctx is not None else None

    agent_tools = (
        build_agent_tools(
            workspace_root=workspace_root,
            user_id=user_id,
            send_fn=None,
            surface="webhook",
        )
        if workspace_root is not None
        else []
    )

    permission_check_fn: PermissionCheckFn | None = None
    if workspace_root is not None:
        permission_context = PermissionContext(
            user_id=str(user_id),
            workspace_root=workspace_root,
            conversation_id=str(uuid.uuid4()),
            surface="webhook",
            enabled_tools=enabled_tools,
        )
        gate = build_default_permission_check()

        async def permission_check_for_handler(
            tool_name: str, arguments: dict[str, Any]
        ) -> PermissionCheckResult:
            decision = await gate(tool_name, arguments, permission_context)
            return PermissionCheckResult(
                allow=decision.allow,
                reason=decision.reason,
                violation_type=decision.violation_type,
            )

        permission_check_fn = permission_check_for_handler

    # resolve_llm does not accept user_id; workspace_root carries the
    # per-user key resolution upstream. Kept for call-site symmetry.
    _ = user_id
    provider = resolve_llm(
        default_model().id,
        workspace_root=workspace_root,
    )

    accumulated: list[str] = [
        stream_event.get("content", "")
        async for stream_event in provider.stream(
            prompt,
            uuid.uuid4(),
            user_id,
            history=[],
            tools=agent_tools or None,
            system_prompt=system_prompt,
            permission_check=permission_check_fn,
        )
        if stream_event.get("type") == "delta"
    ]
    return "".join(accumulated).strip()


async def persist_assistant_response(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    text: str,
    originating_event_id: str,
) -> None:
    """Write the agent's response into a chat conversation as a finalised turn.

    Failures are logged and swallowed: a persistence error must not
    break the Telegram fan-out that follows in the caller. The row is
    written via the same helpers the web chat router uses, so the
    UI's existing ``GET .../messages`` path picks it up immediately.
    """
    try:
        async with async_session_maker() as session:
            placeholder = await append_assistant_placeholder(
                session,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            await finalize_assistant_message(
                session,
                message_id=placeholder.id,
                content=text,
                thinking=None,
                tool_calls=None,
                timeline=None,
                thinking_duration_seconds=None,
                assistant_status="complete",
            )
            await session.commit()
    except Exception:
        logger.exception(
            "AGENT_HANDLER_PERSIST_FAILED conversation_id=%s originating_event_id=%s",
            conversation_id,
            originating_event_id,
        )
