"""Telegram-side adapter for the cross-provider permission gate.

Extracted out of :mod:`app.channels.telegram.bot` to keep that module's
fan-out under the sentrux god-file threshold (15). All the permission
machinery is concentrated here; ``bot.py`` only imports the single
factory function below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.types import PermissionCheckFn, PermissionCheckResult
from app.governance.permissions import (
    PermissionContext,
    build_default_permission_check,
)
from app.governance.workspace_context import load_workspace_context

from .channel import SURFACE_TELEGRAM


def build_telegram_permission_check(
    context: Any,
    workspace_root: Path | None,
) -> PermissionCheckFn | None:
    """Return a permission gate bound to this turn's user / workspace.

    The Telegram path mirrors the chat router's wire-up: a per-request
    :class:`PermissionContext` is fed into
    :func:`build_default_permission_check` and adapted to the
    cross-provider ``(tool_name, arguments)`` signature so the loop's
    permission seam never sees Telegram-specific state.

    Returns ``None`` when no workspace was supplied — the gate has
    nothing to anchor file / bash boundary checks against, so it stays
    a no-op rather than denying every tool call.
    """
    if workspace_root is None:
        return None
    workspace_ctx = load_workspace_context(workspace_root)
    permission_context = PermissionContext(
        user_id=str(context.pawrrtal_user_id),
        workspace_root=workspace_root,
        conversation_id=str(context.conversation_id),
        surface=SURFACE_TELEGRAM,
        enabled_tools=workspace_ctx.enabled_tools,
    )
    gate = build_default_permission_check()

    async def _permission_check(tool_name: str, arguments: dict[str, Any]) -> PermissionCheckResult:
        decision = await gate(tool_name, arguments, permission_context)
        return PermissionCheckResult(
            allow=decision.allow,
            reason=decision.reason,
            violation_type=decision.violation_type,
        )

    return _permission_check
