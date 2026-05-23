"""Utility to load a workspace's identity files as a system-prompt string.

The agent's system prompt is built by concatenating, in order:

  1. ``SOUL.md`` — who the agent is.  Per the workspace convention this
     file is editable by the agent itself, so the system prompt always
     reflects the agent's current self-description.
  2. ``AGENTS.md`` — operating rules + workspace-specific guidance.
  3. ``BOOTSTRAP.md`` — first-run persona setup, only until completed.

Both files live at the workspace root.  Each load returns ``None`` on
failure so the caller can fall back to a hard-coded default per file.

This is intentionally a thin I/O helper — all prompt-assembly decisions
(fallback text, prefix/suffix injection, separators) live in the chat
endpoint.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.fs import read_capped_utf8
from app.core.persona_bootstrap import read_persona_bootstrap

log = logging.getLogger(__name__)

_AGENTS_MD = "AGENTS.md"
_SOUL_MD = "SOUL.md"
_SKILLS_INDEX_MD = "skills/_index.md"
_MAX_BYTES = 64_000  # 64 KB — generous but keeps the context window sane
_SKILLS_INDEX_MAX_BYTES = 32_000  # 32 KB — index only, not skill bodies

# Files the agent must NEVER be able to delete or rename.  Used by the
# workspace_files write tool — see `app/core/tools/workspace_files.py::is_protected_path`.
PROTECTED_FILENAMES: frozenset[str] = frozenset(
    {
        _AGENTS_MD,
        _SOUL_MD,
        "USER.md",
        "IDENTITY.md",
        "MEMORY.md",
        _SKILLS_INDEX_MD,
    }
)


def read_agents_md(workspace_root: Path) -> str | None:
    """Return the text of *workspace_root*/AGENTS.md, or ``None`` on failure."""
    return read_capped_utf8(workspace_root / _AGENTS_MD, max_bytes=_MAX_BYTES)


def read_soul_md(workspace_root: Path) -> str | None:
    """Return the text of *workspace_root*/SOUL.md, or ``None`` on failure.

    SOUL.md is the agent's self-description and is intentionally
    editable by the agent itself — when the agent rewrites it, the next
    turn's system prompt reflects the new identity.
    """
    return read_capped_utf8(workspace_root / _SOUL_MD, max_bytes=_MAX_BYTES)


def read_skills_index(workspace_root: Path) -> str | None:
    """Return the text of *workspace_root*/skills/_index.md, or ``None`` on failure."""
    return read_capped_utf8(workspace_root / _SKILLS_INDEX_MD, max_bytes=_SKILLS_INDEX_MAX_BYTES)


def assemble_workspace_prompt(workspace_root: Path) -> str | None:
    """Return workspace prompt files, or ``None`` if all are missing.

    Order: SOUL.md ("who you are"), AGENTS.md ("how to operate here"),
    BOOTSTRAP.md (only while first-run setup is pending), then skills/_index.md
    ("what skills are available").  Any section may be absent independently;
    missing sections are omitted with no placeholder text so the agent doesn't
    see "(file missing)" noise.
    """
    soul = read_soul_md(workspace_root)
    agents = read_agents_md(workspace_root)
    bootstrap = read_persona_bootstrap(workspace_root)
    skills_index = read_skills_index(workspace_root)
    if soul is None and agents is None and bootstrap is None and skills_index is None:
        return None
    parts: list[str] = []
    if soul is not None:
        parts.append(soul)
    if agents is not None:
        parts.append(agents)
    if bootstrap is not None:
        parts.append(bootstrap)
    if skills_index is not None:
        parts.append(skills_index)
    return "\n\n---\n\n".join(parts)
