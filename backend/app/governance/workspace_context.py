"""Cross-provider workspace-context loader.

Single source of truth for "what does this workspace tell the agent
it can do" — every provider (Claude, Gemini, future) consumes the
same :class:`WorkspaceContext` so a Pawrrtal workspace works the same
across all backends.

What we read
------------
1. **System prompt** — concatenation of (in order), via
   :func:`app.tools.agents_md.assemble_workspace_prompt`:
   * ``SOUL.md`` — durable Paw identity.
   * ``AGENTS.md`` — operating contract.
   * ``USER.md`` — user profile.
   * ``PREFERENCES.md`` — standing preferences and bootstrap state.
   * ``.agent/skills/paw-bootstrap/SKILL.md`` — first-run Paw persona
     setup, only until the identity block in PREFERENCES.md flips
     ``bootstrap_completed: true``.
   * ``.agent/skills/_index.md`` — the always-in-context skill map.
2. **Skills** — one ``SkillDef`` per skill listed by
   ``.agent/skills/_manifest.jsonl`` when present, otherwise by
   backwards-compatible directory discovery. By default the system
   prompt gets a compact manifest of skill names, descriptions, and
   paths; full SKILL.md bodies remain available through the workspace
   skill tools and can be restored with ``WORKSPACE_SKILL_PROMPT_MODE=full``.
3. **Permissions** — ``.agent/protocols/permissions.md`` is appended
   to the prompt for conversational guidance only. There is no
   mechanical allow/deny gate; the agent honours the file's guidance
   conversationally.

Writes
------
None — pure read.  The `WorkspaceContext` is built fresh per chat
request (workspaces are small enough that the I/O cost is negligible
and the freshness avoids cache invalidation entirely).

Failure mode
------------
Every individual file load tolerates a missing file → ``None``.  An
empty workspace yields a default-shaped :class:`WorkspaceContext` with
no system prompt.  Callers can always check ``ctx.is_empty`` to decide
whether to short-circuit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.config import settings
from app.infrastructure.fs import read_capped_utf8
from app.tools.agents_md import (
    assemble_workspace_prompt,
)
from app.tools.skills import read_skill_manifest
from app.workspace.persona_bootstrap import is_persona_bootstrap_pending

logger = logging.getLogger(__name__)

# Generous cap on individual file reads — same as the AGENTS.md loader
# so a workspace can't blow the context window with a 10MB SKILL.md.
_MAX_BYTES = 64_000

# Per-skill manifest filename. Each ``.agent/skills/<name>/SKILL.md``
# contributes one :class:`SkillDef` to the catalogue.
_SKILL_MANIFEST = "SKILL.md"

# Section heading injected into the system prompt when the workspace
# has at least one skill. Kept short so it doesn't fight with the
# operating-rules text from AGENTS.md.
_SKILLS_HEADING = "## Available Skills"
_SKILLS_OFF_MODES = {"", "off", "none", "false", "0"}
_SKILLS_FULL_MODE = "full"


@dataclass(frozen=True)
class SkillDef:
    """One skill the workspace exposes via ``.agent/skills/<name>/SKILL.md``.

    Skills are surfaced into the system prompt as a catalogue so
    providers without native skill auto-invocation (Gemini, future)
    can still let the model decide when to "call" a skill (i.e. ask
    the user to follow its instructions). Auto-invocation lives in
    a future PR with a classifier.
    """

    name: str
    description: str | None
    body: str
    path: Path


@dataclass(frozen=True)
class WorkspaceContext:
    """Single struct every provider consumes.

    Built fresh per chat request via :func:`load_workspace_context`.
    Providers consume ``system_prompt`` (Claude additionally enables
    ``setting_sources=['project']`` so the SDK reads the same files
    natively — defence in depth).
    """

    system_prompt: str | None
    skills: tuple[SkillDef, ...]
    loaded_from: tuple[Path, ...]

    @property
    def is_empty(self) -> bool:
        """``True`` when nothing was loaded from the workspace.

        A caller seeing ``is_empty`` can fall back to whatever default
        the provider had before workspace context existed.
        """
        return self.system_prompt is None and not self.skills


def load_workspace_context(root: Path) -> WorkspaceContext:
    """Read the workspace's prompt + skills + permissions in one pass.

    No-op when ``settings.workspace_context_enabled`` is False — the
    caller can keep the call site unchanged and just see an empty
    context. Logs at DEBUG for every path actually loaded so the
    operator can verify a deploy reads what they expect.
    """
    if not settings.workspace_context_enabled:
        return _empty_context()

    loaded: list[Path] = []
    base_prompt = assemble_workspace_prompt(root)
    if base_prompt is not None:
        # ``assemble_workspace_prompt`` concatenates root context files,
        # the paw-bootstrap skill body (while pending), and skills/_index.md.
        for filename in ("SOUL.md", "AGENTS.md", "USER.md", "PREFERENCES.md"):
            path = root / filename
            if read_capped_utf8(path, max_bytes=_MAX_BYTES) is not None:
                loaded.append(path)
        bootstrap_path = root / ".agent/skills/paw-bootstrap/SKILL.md"
        if (
            is_persona_bootstrap_pending(root)
            and read_capped_utf8(bootstrap_path, max_bytes=_MAX_BYTES) is not None
        ):
            loaded.append(bootstrap_path)
        skills_index_path = root / ".agent/skills/_index.md"
        if read_capped_utf8(skills_index_path, max_bytes=_MAX_BYTES) is not None:
            loaded.append(skills_index_path)

    skills = _load_skills(root, loaded)
    permissions_text = _load_permissions(root, loaded)

    system_prompt = _assemble_system_prompt(
        base_prompt=base_prompt,
        permissions_text=permissions_text,
        skills=skills,
    )

    if loaded:
        logger.debug(
            "WORKSPACE_CONTEXT_LOADED root=%s files=%s skills=%d skill_prompt_mode=%s "
            "prompt_chars=%d",
            root,
            [str(p.relative_to(root)) for p in loaded],
            len(skills),
            _skill_prompt_mode(),
            len(system_prompt or ""),
        )

    return WorkspaceContext(
        system_prompt=system_prompt,
        skills=tuple(skills),
        loaded_from=tuple(loaded),
    )


def _empty_context() -> WorkspaceContext:
    """Default-shaped context — used when the loader is disabled."""
    return WorkspaceContext(
        system_prompt=None,
        skills=(),
        loaded_from=(),
    )


def _load_skills(root: Path, loaded: list[Path]) -> list[SkillDef]:
    """Load the exposed skill catalog and parse each SKILL.md into a SkillDef."""
    skills_dir = root / settings.workspace_skills_dir_name
    if not skills_dir.exists() or not skills_dir.is_dir():
        return []
    skills: list[SkillDef] = []
    for entry in read_skill_manifest(root):
        if not entry.has_skill_md:
            continue
        manifest_path = skills_dir / entry.name / _SKILL_MANIFEST
        body = read_capped_utf8(manifest_path, max_bytes=_MAX_BYTES)
        if body is None:
            continue
        skill = _parse_skill_manifest(name=entry.name, path=manifest_path, body=body)
        if skill is not None:
            skills.append(skill)
            loaded.append(manifest_path)
    return skills


def _parse_skill_manifest(*, name: str, path: Path, body: str) -> SkillDef | None:
    """Parse a single SKILL.md.

    The skill schema is loose — the canonical form has a YAML
    frontmatter block (``--- ... ---``) with ``name`` and
    ``description`` keys, but we don't depend on the YAML library
    here.  We extract a ``description: ...`` line if present and
    keep the whole body for prompt injection.
    """
    description = _extract_description(body)
    return SkillDef(
        name=name,
        description=description,
        body=body,
        path=path,
    )


def _extract_description(body: str) -> str | None:
    """Pull the first ``description: ...`` line out of a SKILL.md body."""
    for line in body.splitlines()[:30]:
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            return stripped.split(":", 1)[1].strip() or None
    return None


def _load_permissions(root: Path, loaded: list[Path]) -> str | None:
    """Read ``.agent/protocols/permissions.md`` for prompt context.

    Returns ``None`` when the file is missing. When present and
    readable, the file is recorded in ``loaded`` and appended to the
    prompt for conversational guidance only — there is no mechanical
    allow/deny gate.
    """
    settings_path = root / settings.workspace_settings_filename
    text = read_capped_utf8(settings_path, max_bytes=_MAX_BYTES)
    if text is None:
        return None
    loaded.append(settings_path)
    return f"## Workspace Permissions\n\n{text}"


def _assemble_system_prompt(
    *,
    base_prompt: str | None,
    permissions_text: str | None,
    skills: list[SkillDef],
) -> str | None:
    """Concatenate the base prompt + skills catalogue.

    Order matches the load priority: AGENTS.md + bootstrap +
    skills/_index.md (already concatenated by
    ``assemble_workspace_prompt``) -> skills catalogue. Returns
    ``None`` when neither contributed text.
    """
    parts: list[str] = []
    if base_prompt is not None:
        parts.append(base_prompt)
    if permissions_text is not None:
        parts.append(permissions_text)
    if skills and _skill_prompt_mode() not in _SKILLS_OFF_MODES:
        parts.append(_format_skills_catalogue(skills))
    if not parts:
        return None
    return "\n\n---\n\n".join(parts)


def _format_skills_catalogue(skills: list[SkillDef]) -> str:
    """Render a skill list as a Markdown section the model can read.

    The default manifest mode keeps provider prompts responsive: it
    includes discovery metadata only and relies on the workspace skill
    tools for full bodies. Operators can set
    ``WORKSPACE_SKILL_PROMPT_MODE=full`` to restore the legacy full-body
    prompt injection.
    """
    lines: list[str] = [_SKILLS_HEADING, ""]
    for skill in skills:
        lines.append(f"### {skill.name}")
        if skill.description:
            lines.append(skill.description)
        lines.append(f"Path: `{_relative_skill_path(skill)}`")
        if _skill_prompt_mode() == _SKILLS_FULL_MODE:
            lines.append("")
            lines.append(skill.body.strip())
        lines.append("")
    return "\n".join(lines).rstrip()


def _skill_prompt_mode() -> str:
    """Return the normalized workspace skill prompt mode."""
    return str(settings.workspace_skill_prompt_mode or "manifest").strip().lower()


def _relative_skill_path(skill: SkillDef) -> str:
    """Return a stable workspace-relative-ish path for prompt display."""
    parts = skill.path.parts
    try:
        idx = parts.index(".agent")
    except ValueError:
        return skill.path.name
    return "/".join(parts[idx:])
