"""Workspace prompt assembly for channel turns."""

from __future__ import annotations

from pathlib import Path

from app.core.agent_system_prompt import compose_agent_system_prompt
from app.core.governance.workspace_context import load_workspace_context
from app.core.persona_bootstrap import ensure_persona_bootstrap_seeded
from app.core.tools.agents_md import assemble_workspace_prompt


def workspace_system_prompt(workspace_root: Path | None) -> str | None:
    """Load workspace prompt files when a workspace root is available.

    PR 06 — uses :func:`load_workspace_context` so SOUL.md / AGENTS.md /
    CLAUDE.md and ``.claude/skills/`` are merged into one provider-
    neutral system prompt. Falls back to the legacy
    :func:`assemble_workspace_prompt` builder when WorkspaceContext is
    disabled or returns nothing so existing deployments don't lose
    their AGENTS.md content.
    """
    if workspace_root is None:
        return compose_agent_system_prompt(None)
    ensure_persona_bootstrap_seeded(workspace_root)
    workspace_ctx = load_workspace_context(workspace_root)
    if workspace_ctx.system_prompt is not None:
        return compose_agent_system_prompt(workspace_ctx.system_prompt)
    return compose_agent_system_prompt(assemble_workspace_prompt(workspace_root))
