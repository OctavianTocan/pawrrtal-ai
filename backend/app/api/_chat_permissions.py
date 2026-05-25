"""Per-request permission-gate builder for ``/api/v1/chat``.

Extracted from :mod:`app.api.chat` to keep that module's fan-out
under the sentrux god-file threshold (15). The chat router needs
three governance/loop modules to assemble a per-turn permission
gate (``permissions``, ``workspace_context``, ``agent_loop.types``);
hoisting the wiring here removes those edges from chat.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from app.api._chat_external_mcp import (
    # Re-export keeps chat.py fan-out under sentrux budget.
    load_external_mcp_configs as load_external_mcp_configs,  # noqa: PLC0414
)
from app.core.agent_loop.types import PermissionCheckFn, PermissionCheckResult
from app.core.governance.permissions import (
    PermissionContext,
    build_default_permission_check,
)
from app.core.governance.workspace_context import load_workspace_context


def build_chat_permission_check(
    *,
    user_id: UUID,
    workspace_root: Path,
    conversation_id: UUID,
    surface: str,
) -> PermissionCheckFn:
    """Build a per-request ``PermissionCheckFn`` for the chat router.

    ``PermissionContext`` captures workspace + user + surface so the
    gate's individual checks (file-path boundary, bash boundary,
    workspace allowlist) have the state they need; the returned
    closure adapts the cross-provider ``(tool_name, arguments)``
    signature so the context never leaks into the agent loop. Both
    providers consume the same closure — Claude via the SDK's
    ``can_use_tool`` hook, Gemini via
    :class:`~app.core.agent_loop.types.AgentLoopConfig.permission_check`.

    Workspace context drives ``enabled_tools`` so the gate respects
    the workspace's ``.agent/protocols/permissions.md`` allow list
    once a Markdown parser is wired in.
    """
    workspace_ctx = load_workspace_context(workspace_root)
    permission_context = PermissionContext(
        user_id=str(user_id),
        workspace_root=workspace_root,
        conversation_id=str(conversation_id),
        surface=surface,
        enabled_tools=workspace_ctx.enabled_tools,
    )
    gate = build_default_permission_check()

    async def permission_check(tool_name: str, arguments: dict[str, Any]) -> PermissionCheckResult:
        decision = await gate(tool_name, arguments, permission_context)
        return PermissionCheckResult(
            allow=decision.allow,
            reason=decision.reason,
            violation_type=decision.violation_type,
        )

    return permission_check
