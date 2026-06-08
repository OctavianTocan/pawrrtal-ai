"""Workspace prompt assembly for channel turns."""

from __future__ import annotations

from pathlib import Path

from app.agents import compose_agent_system_prompt
from app.governance.workspace_context import load_workspace_context
from app.tools.agents_md import assemble_workspace_prompt


def workspace_system_prompt(workspace_root: Path | None) -> str | None:
    """Load workspace prompt files when a workspace root is available.

    Uses :func:`load_workspace_context` so root prompt files and the
    Paw skill catalogue (plus the bootstrap skill when the identity
    block is still pending) are merged into one provider-neutral system prompt. Falls back to
    :func:`assemble_workspace_prompt` when WorkspaceContext is disabled.
    """
    if workspace_root is None:
        return compose_agent_system_prompt(None)
    workspace_ctx = load_workspace_context(workspace_root)
    if workspace_ctx.system_prompt is not None:
        return compose_agent_system_prompt(workspace_ctx.system_prompt)
    return compose_agent_system_prompt(assemble_workspace_prompt(workspace_root))
