"""Cross-provider workspace-context loader.

Single source of truth for "what does this workspace tell the agent
it can do" — every provider (Claude, Gemini, future) consumes the
same :class:`WorkspaceContext` so a Claude-Code-native workspace
dropped into the SaaS just works for non-Claude models too.

What we read
------------
1. **System prompt** — concatenation of (in order):
   * ``SOUL.md`` — agent identity (the existing
     :func:`app.core.tools.agents_md.assemble_workspace_prompt` covers
     this and AGENTS.md; we add CLAUDE.md compatibility on top).
   * ``AGENTS.md`` — operating rules.
   * ``BOOTSTRAP.md`` — first-run Paw persona setup, only until completed.
   * ``CLAUDE.md`` — Claude Code-native operating manual.  Loaded so
     a workspace authored against the Claude Code CLI works the same
     against our Gemini path.
2. **Skills** — one ``SkillDef`` per ``.claude/skills/<name>/SKILL.md``.
   The body of each SKILL.md is appended to the system prompt under
   a "## Available Skills" section so providers without native skill
   loading (Gemini, future) still surface the skill catalogue.
3. **Permissions** — parsed from ``.claude/settings.json`` (Claude
   Code's permissions schema: ``permissions.allow``, ``permissions.deny``,
   ``permissions.defaultMode``).  Mapped onto an
   ``enabled_tools: frozenset[str] | None`` the cross-provider
   permission gate (PR 03) consults.

Writes
------
None — pure read.  The `WorkspaceContext` is built fresh per chat
request (workspaces are small enough that the I/O cost is negligible
and the freshness avoids cache invalidation entirely).

Failure mode
------------
Every individual file load tolerates a missing file → ``None``.  An
empty workspace yields a default-shaped :class:`WorkspaceContext` with
no system prompt and no allowlist (i.e. the historical "trust
everything" behaviour).  Callers can always check ``ctx.is_empty`` to
decide whether to short-circuit.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.fs import read_capped_utf8
from app.core.persona_bootstrap import is_persona_bootstrap_pending
from app.core.tools.agents_md import (
    assemble_workspace_prompt,
)

logger = logging.getLogger(__name__)

# Generous cap on individual file reads — same as the AGENTS.md loader
# so a workspace can't blow the context window with a 10MB SKILL.md.
_MAX_BYTES = 64_000

# Workspace-relative path to the canonical Claude Code-native operating
# manual.  Read in addition to SOUL.md / AGENTS.md so a workspace
# authored against the Claude Code CLI keeps working.
_CLAUDE_MD = "CLAUDE.md"

# Per-skill manifest filename.  Each ``.claude/skills/<name>/SKILL.md``
# contributes one :class:`SkillDef` to the catalogue.
_SKILL_MANIFEST = "SKILL.md"

# Section heading injected into the system prompt when the workspace
# has at least one skill.  Kept short so it doesn't fight with the
# operating-rules text from AGENTS.md / CLAUDE.md.
_SKILLS_HEADING = "## Available Skills"


@dataclass(frozen=True)
class SkillDef:
    """One skill the workspace exposes via ``.claude/skills/<name>/SKILL.md``.

    Skills are surfaced into the system prompt as a catalogue so
    providers without native skill auto-invocation (Gemini, future)
    can still let the model decide when to "call" a skill (i.e. ask
    the user to follow its instructions).  Auto-invocation lives in
    a future PR with a classifier.
    """

    name: str
    description: str | None
    body: str
    path: Path


@dataclass(frozen=True)
class SettingsPermissions:
    """Parsed ``permissions`` block from ``.claude/settings.json``.

    Mirrors Claude Code's published schema:
    https://docs.anthropic.com/en/docs/claude-code/settings#permissions

    ``allow`` and ``deny`` are *tool name patterns* — the cross-provider
    gate currently treats them as exact tool names; pattern semantics
    (``Bash(npm test)``, etc.) are a future PR.
    """

    allow: frozenset[str] = field(default_factory=frozenset)
    deny: frozenset[str] = field(default_factory=frozenset)
    default_mode: str | None = None


@dataclass(frozen=True)
class WorkspaceContext:
    """Single struct every provider + permission gate consumes.

    Built fresh per chat request via :func:`load_workspace_context`.
    The cross-provider permission gate consults ``enabled_tools``;
    providers consume ``system_prompt`` (Claude additionally enables
    ``setting_sources=['project']`` so the SDK reads the same files
    natively — defence in depth).
    """

    system_prompt: str | None
    enabled_tools: frozenset[str] | None
    skills: tuple[SkillDef, ...]
    permissions: SettingsPermissions
    loaded_from: tuple[Path, ...]

    @property
    def is_empty(self) -> bool:
        """``True`` when nothing was loaded from the workspace.

        A caller seeing ``is_empty`` can fall back to whatever default
        the provider had before workspace context existed.
        """
        return (
            self.system_prompt is None
            and self.enabled_tools is None
            and not self.skills
            and not self.permissions.allow
            and not self.permissions.deny
        )


def load_workspace_context(root: Path) -> WorkspaceContext:
    """Read the workspace's prompt + skills + permissions in one pass.

    No-op when ``settings.workspace_context_enabled`` is False — the
    caller can keep the call site unchanged and just see an empty
    context.  Logs at DEBUG for every path actually loaded so the
    operator can verify a deploy reads what they expect.
    """
    if not settings.workspace_context_enabled:
        return _empty_context()

    loaded: list[Path] = []
    base_prompt = assemble_workspace_prompt(root)
    if base_prompt is not None:
        # ``assemble_workspace_prompt`` already concatenates SOUL.md,
        # AGENTS.md, pending BOOTSTRAP.md, and skills/_index.md; we
        # record the source paths if they exist.
        loaded.extend(root / name for name in ("SOUL.md", "AGENTS.md") if (root / name).exists())
        if is_persona_bootstrap_pending(root):
            loaded.append(root / "BOOTSTRAP.md")
        if (root / "skills/_index.md").exists():
            loaded.append(root / "skills/_index.md")

    claude_md = read_capped_utf8(root / _CLAUDE_MD, max_bytes=_MAX_BYTES)
    if claude_md is not None:
        loaded.append(root / _CLAUDE_MD)

    skills = _load_skills(root, loaded)
    permissions = _load_permissions(root, loaded)

    system_prompt = _assemble_system_prompt(
        base_prompt=base_prompt,
        claude_md=claude_md,
        skills=skills,
    )
    enabled_tools = _resolve_enabled_tools(permissions)

    if loaded:
        logger.debug(
            "WORKSPACE_CONTEXT_LOADED root=%s files=%s skills=%d allow=%d deny=%d",
            root,
            [str(p.relative_to(root)) for p in loaded],
            len(skills),
            len(permissions.allow),
            len(permissions.deny),
        )

    return WorkspaceContext(
        system_prompt=system_prompt,
        enabled_tools=enabled_tools,
        skills=tuple(skills),
        permissions=permissions,
        loaded_from=tuple(loaded),
    )


def _empty_context() -> WorkspaceContext:
    """Default-shaped context — used when the loader is disabled."""
    return WorkspaceContext(
        system_prompt=None,
        enabled_tools=None,
        skills=(),
        permissions=SettingsPermissions(),
        loaded_from=(),
    )


def _load_skills(root: Path, loaded: list[Path]) -> list[SkillDef]:
    """Walk ``.claude/skills/*/SKILL.md`` and parse each into a SkillDef."""
    skills_dir = root / settings.workspace_skills_dir_name
    if not skills_dir.exists() or not skills_dir.is_dir():
        return []
    skills: list[SkillDef] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / _SKILL_MANIFEST
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


def _load_permissions(root: Path, loaded: list[Path]) -> SettingsPermissions:
    """Parse ``.claude/settings.json`` permissions block.

    Returns the default-shaped :class:`SettingsPermissions` when the
    file is missing or malformed — workspaces without an explicit
    settings file accept every registered tool (matches PR 03's
    "permissive by default" plan).
    """
    settings_path = root / settings.workspace_settings_filename
    if not settings_path.exists():
        return SettingsPermissions()
    try:
        raw = read_capped_utf8(settings_path, max_bytes=_MAX_BYTES)
        if raw is None:
            return SettingsPermissions()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "WORKSPACE_SETTINGS_PARSE_FAILED path=%s error=%s",
            settings_path,
            exc,
        )
        return SettingsPermissions()
    perms = payload.get("permissions") if isinstance(payload, dict) else None
    if not isinstance(perms, dict):
        return SettingsPermissions()
    loaded.append(settings_path)
    return SettingsPermissions(
        allow=frozenset(_as_str_iter(perms.get("allow"))),
        deny=frozenset(_as_str_iter(perms.get("deny"))),
        default_mode=_as_optional_str(perms.get("defaultMode")),
    )


def _as_str_iter(value: object) -> list[str]:
    """Coerce a JSON value into a list of strings (filters out non-strings)."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _assemble_system_prompt(
    *,
    base_prompt: str | None,
    claude_md: str | None,
    skills: list[SkillDef],
) -> str | None:
    """Concatenate the base prompt + CLAUDE.md + skills catalogue.

    Order matches the load priority: SOUL.md + AGENTS.md (already
    concatenated by ``assemble_workspace_prompt``) → CLAUDE.md →
    skills catalogue.  Returns ``None`` when none of the three
    sources contributed text.
    """
    parts: list[str] = []
    if base_prompt is not None:
        parts.append(base_prompt)
    if claude_md is not None:
        parts.append(claude_md)
    if skills:
        parts.append(_format_skills_catalogue(skills))
    if not parts:
        return None
    return "\n\n---\n\n".join(parts)


def _format_skills_catalogue(skills: list[SkillDef]) -> str:
    """Render a skill list as a Markdown section the model can read.

    Includes the description (when present) and the full body of each
    skill so the model can decide when to follow it.  For long skills
    this can grow the prompt — operators can drop the ``.claude/skills/``
    directory or set ``WORKSPACE_CONTEXT_ENABLED=false`` to disable.
    """
    lines: list[str] = [_SKILLS_HEADING, ""]
    for skill in skills:
        lines.append(f"### {skill.name}")
        if skill.description:
            lines.append(skill.description)
            lines.append("")
        lines.append(skill.body.strip())
        lines.append("")
    return "\n".join(lines).rstrip()


def _resolve_enabled_tools(perms: SettingsPermissions) -> frozenset[str] | None:
    """Compute the tool allowlist the cross-provider gate consults.

    Returns:
        ``None`` when the workspace has no opinion (empty allow/deny)
        — the gate falls through to "permissive". Otherwise an
        explicit allowlist (allow minus deny) the gate enforces.
    """
    if not perms.allow and not perms.deny:
        return None
    if not perms.allow:
        # Pure-deny semantics: every known tool is allowed except
        # the explicit deny list.  We can't materialise "every known
        # tool" here without the chat router's tool list, so return
        # ``None`` and let the gate enforce the deny list separately
        # (PR 06 follow-on; for now deny-only workspaces accept
        # everything).
        return None
    allowed = perms.allow - perms.deny
    return frozenset(allowed)
