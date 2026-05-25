"""Agent-facing tools for skill discovery + invocation (#315).

The workspace already ships a manifest reader at
:mod:`app.core.tools.skills` that powers the ``/api/v1/workspace/skills``
endpoint. This module wraps the same reader plus a bounded
``SKILL.md`` reader as ``AgentTool`` factories so the Paw can:

* list available skills (``list_skills``);
* read one selected ``SKILL.md`` body bounded by line + byte caps
  (``read_skill``);
* invoke a skill workflow as a turn-scoped instruction injection
  (``invoke_skill``) — the Paw receives the SKILL.md instructions
  with a header noting that the user explicitly chose to apply
  the skill, and the next turn-level reasoning treats those
  instructions as the playbook.

Why three tools instead of one ``run_skill`` ? Following the design
notes on the issue: discovery and reading should be cheap and
auditable; invocation should be explicit. Splitting also lets the
agent stage decisions: ``list_skills`` → ``read_skill`` → confirm
with user → ``invoke_skill``.

All filesystem access is scoped to ``workspace_root / skills``.
``..`` traversal and absolute paths are rejected by
:func:`_resolve_skill_path` with a ``ToolError(OUT_OF_ROOT)``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.tools.display import make_tool_display
from app.core.tools.errors import ToolError, ToolErrorCode
from app.core.tools.skills import read_skill_manifest

log = logging.getLogger(__name__)

# Hard caps on what we read into the agent prompt. Skills that ship
# huge ``SKILL.md`` files (rare but possible) get truncated so the
# agent doesn't blow its context budget on a single skill.
_MAX_SKILL_BODY_BYTES = 32_000
_MAX_SKILL_BODY_LINES = 800
_SKILL_MD_NAME = "SKILL.md"
_SKILLS_DIR = ".agent/skills"


def _resolve_skill_path(workspace_root: Path, skill_name: str) -> Path:
    """Resolve ``workspace_root/skills/<skill_name>/SKILL.md`` safely.

    Rejects ``..`` traversal, absolute names, and any resolved path
    that escapes the ``skills`` directory. Raises
    :class:`ToolError(OUT_OF_ROOT)` on violation so the agent gets a
    clear, stable error message instead of an obscure ``ValueError``.
    """
    if not skill_name or "/" in skill_name or "\\" in skill_name or skill_name.startswith("."):
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"Skill name {skill_name!r} is not a simple skill identifier.",
        )
    skills_root = (workspace_root / _SKILLS_DIR).resolve()
    target = (skills_root / skill_name / _SKILL_MD_NAME).resolve()
    if not str(target).startswith(str(skills_root) + "/") and target != skills_root:
        raise ToolError(
            ToolErrorCode.OUT_OF_ROOT,
            f"Skill {skill_name!r} resolves outside the workspace skills directory.",
        )
    return target


def _bounded_body(text: str) -> tuple[str, bool]:
    """Return ``(body, truncated)`` capped by line + byte limits."""
    lines = text.splitlines()
    truncated_by_lines = False
    if len(lines) > _MAX_SKILL_BODY_LINES:
        lines = lines[:_MAX_SKILL_BODY_LINES]
        truncated_by_lines = True
    body = "\n".join(lines)
    truncated_by_bytes = False
    encoded = body.encode("utf-8")
    if len(encoded) > _MAX_SKILL_BODY_BYTES:
        body = encoded[:_MAX_SKILL_BODY_BYTES].decode("utf-8", errors="ignore")
        truncated_by_bytes = True
    return body, truncated_by_lines or truncated_by_bytes


def make_list_skills_tool(*, workspace_root: Path) -> AgentTool:
    """Return ``list_skills`` :class:`AgentTool` bound to *workspace_root*."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        entries = read_skill_manifest(Path(workspace_root))
        if not entries:
            return "No skills are configured for this workspace."
        rows: list[str] = []
        for entry in entries:
            marker = "" if entry.has_skill_md else " (no SKILL.md)"
            rows.append(f"- {entry.name}{marker}: trigger={entry.trigger}; summary={entry.summary}")
        return "\n".join(rows)

    return AgentTool(
        name="list_skills",
        description=(
            "List the skills configured in the user's workspace. "
            "Each row shows the skill name, the trigger phrase the user "
            "would type to invoke it, and a one-line summary. Use "
            "before read_skill or invoke_skill so you know which "
            "skill exists."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        execute=execute,
        display=make_tool_display(
            icon="📚",
            label="List skills",
            present=lambda _args: "📚 Listing workspace skills",
            compact=lambda _args: "list_skills()",
        ),
    )


def make_read_skill_tool(*, workspace_root: Path) -> AgentTool:
    """Return ``read_skill`` :class:`AgentTool` bound to *workspace_root*."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        name = str(kwargs.get("name") or "").strip()
        if not name:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "The 'name' argument is required.",
            ).render()
        try:
            target = _resolve_skill_path(Path(workspace_root), name)
        except ToolError as err:
            return err.render()
        if not target.is_file():
            return ToolError(
                ToolErrorCode.NOT_FOUND,
                f"Skill {name!r} has no SKILL.md at {target.parent}.",
            ).render()
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolError(
                ToolErrorCode.IO_ERROR,
                f"Could not read SKILL.md for {name!r}: {exc}",
            ).render()
        body, truncated = _bounded_body(text)
        suffix = "\n\n[truncated]" if truncated else ""
        return f"# Skill: {name}\n\n{body}{suffix}"

    return AgentTool(
        name="read_skill",
        description=(
            "Read the SKILL.md instructions for one workspace skill. "
            "Use after list_skills to inspect what the skill does "
            "before invoking it. Returns the Markdown body capped at "
            f"{_MAX_SKILL_BODY_LINES} lines / {_MAX_SKILL_BODY_BYTES} bytes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Skill identifier as listed by list_skills "
                        "(the directory name under workspace skills/)."
                    ),
                }
            },
            "required": ["name"],
        },
        execute=execute,
        display=make_tool_display(
            icon="📖",
            label="Read skill",
            present=lambda args: f"📖 Reading skill: {args.get('name') or '(missing)'}",
            compact=lambda args: f"read_skill({args.get('name') or ''})",
        ),
    )


def make_invoke_skill_tool(*, workspace_root: Path) -> AgentTool:
    """Return ``invoke_skill`` :class:`AgentTool` bound to *workspace_root*.

    Invocation in v1 is **instruction injection**: the tool returns the
    bounded ``SKILL.md`` body wrapped in a header that tells the agent
    "you have explicitly chosen to apply skill X — follow these
    instructions for the next steps." The agent loop then reasons
    over the injected playbook on the next turn.

    This intentionally avoids running arbitrary scripts from the
    workspace. If the operator later wants `invoke_skill` to execute
    a script step (a future ``SKILL.run`` block), it can be added as
    a second tool with explicit permission gating.
    """

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        name = str(kwargs.get("name") or "").strip()
        reason = str(kwargs.get("reason") or "").strip()
        if not name:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "The 'name' argument is required.",
            ).render()
        try:
            target = _resolve_skill_path(Path(workspace_root), name)
        except ToolError as err:
            return err.render()
        if not target.is_file():
            return ToolError(
                ToolErrorCode.NOT_FOUND,
                f"Skill {name!r} has no SKILL.md to invoke.",
            ).render()
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolError(
                ToolErrorCode.IO_ERROR,
                f"Could not load SKILL.md for {name!r}: {exc}",
            ).render()
        body, truncated = _bounded_body(text)
        suffix = "\n\n[truncated]" if truncated else ""
        reason_block = f"\nReason supplied: {reason}\n" if reason else ""
        log.info("SKILL_INVOKED name=%s reason=%r", name, reason or "")
        return (
            f"Invoking skill {name!r}.{reason_block}"
            "\n--- BEGIN SKILL INSTRUCTIONS ---\n"
            f"{body}{suffix}\n"
            "--- END SKILL INSTRUCTIONS ---\n"
            "Follow the instructions above for the user's request. "
            "Stop using the skill once the workflow it describes is "
            "complete."
        )

    return AgentTool(
        name="invoke_skill",
        description=(
            "Apply a workspace skill as the playbook for the next steps. "
            "Returns the SKILL.md instructions wrapped in a clear "
            "BEGIN / END SKILL INSTRUCTIONS block. Use only when the "
            "user has clearly asked to apply the skill, or when the "
            "user's request matches the skill's documented trigger."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill identifier from list_skills.",
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "Short note explaining why this skill is the "
                        "right one for the user's current ask. Logged "
                        "for audit; visible in the stream timeline."
                    ),
                },
            },
            "required": ["name"],
        },
        execute=execute,
        display=make_tool_display(
            icon="✨",
            label="Invoke skill",
            present=lambda args: f"✨ Invoking skill: {args.get('name') or '(missing)'}",
            compact=lambda args: f"invoke_skill({args.get('name') or ''})",
        ),
    )
