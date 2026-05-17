"""Persona loader, validator, and per-spawn resolver.

A *persona* is a declarative subagent template authored as a markdown
file with YAML frontmatter.  Built-in personas live under
``backend/app/agents/*.md`` and are loaded once at FastAPI startup;
workspace-shipped overrides live under
``<workspace_root>/.pawrrtal/agents/*.md`` and are read lazily per
spawn, with an mtime cache to avoid re-parsing on every chat turn.

The persona is a **capability cap**, not a grant.  At spawn time the
parent agent picks the subset of the persona's ``tools_allow`` it
wants to delegate; the runner then intersects that subset with the
parent's own resolved tool catalogue.  See
``.beans/pawrrtal-subagents-epic.md`` for the full chain.

Resolution precedence (highest wins):

  1. Workspace override   ``<workspace>/.pawrrtal/agents/<name>.md``
  2. Built-in             ``backend/app/agents/<name>.md``

A persona file is **structurally rejected** if it names a model not in
``app.core.providers.catalog.MODEL_CATALOG`` or a tool not in
``KNOWN_TOOL_NAMES`` — startup fails for built-ins (the right place to
catch schema drift), and ``resolve_persona`` returns a ``PersonaError``
for workspace overrides (a single bad workspace must not crash the app).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.providers.catalog import require_known
from app.core.providers.model_id import InvalidModelId, UnknownModelId

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool name registry
# ---------------------------------------------------------------------------

#: The canonical set of tool names a persona may declare in
#: ``tools_allow``.  Kept in sync by hand with the factories under
#: ``backend/app/core/tools/`` — every ``AgentTool(name=...)`` literal
#: produced by ``app.core.agent_tools.build_agent_tools`` must appear
#: here.  Sourced from ``grep 'name="' backend/app/core/tools/`` on
#: 2026-05-17; the tests in ``test_subagent_persona.py`` re-derive
#: this list from the runtime catalogue and fail if the two drift.
KNOWN_TOOL_NAMES: frozenset[str] = frozenset(
    {
        # Workspace filesystem
        "read_file",
        "write_file",
        "list_dir",
        # Web search
        "exa_search",
        # Artifact rendering
        "render_artifact",
        # Image generation
        "generate_image",
        # Document conversion
        "convert_to_markdown",
        # Channel delivery
        "send_message",
        "send_image_to_user",
        "send_voice_to_user",
        "send_document_to_user",
        # LCM history tools
        "lcm_grep",
        "lcm_list_summaries",
        "lcm_describe",
        "lcm_expand_query",
    }
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Directory containing built-in persona markdown files, relative to repo root.
_BUILTIN_PERSONAS_DIR: Path = Path(__file__).resolve().parents[2] / "agents"

#: Subdirectory within a workspace that holds override personas.
_WORKSPACE_PERSONAS_SUBDIR: str = ".pawrrtal/agents"

#: Frontmatter fence used by the markdown loader.
_FRONTMATTER_FENCE: str = "---"

#: Minimum lines a valid persona file needs (open fence + ≥1 frontmatter
#: line + close fence + at least one prompt line).
_MIN_PERSONA_LINES: int = 4

#: Clamp ceilings for persona-declared safety knobs.  Personas can ask
#: for less than these but never more — the runner clamps at spawn time.
PERSONA_MAX_ITERATIONS_CEILING: int = 100
PERSONA_MAX_WALL_CLOCK_CEILING_SECONDS: float = 1800.0

#: Default safety knobs when a persona omits them.
_DEFAULT_PERSONA_MAX_ITERATIONS: int = 50
_DEFAULT_PERSONA_MAX_WALL_CLOCK_SECONDS: float = 600.0

ReasoningEffort = Literal["low", "medium", "high", "extra-high"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PersonaError(ValueError):
    """Raised when a persona file is malformed or references unknown ids.

    Callers convert this into a user-visible error string for workspace
    overrides; the built-in loader re-raises so FastAPI startup fails fast.
    """


# ---------------------------------------------------------------------------
# Schema (Pydantic) + runtime dataclass
# ---------------------------------------------------------------------------


class _PersonaSpec(BaseModel):
    """YAML-frontmatter schema for a persona file.

    Private — callers receive the immutable :class:`Persona` dataclass,
    not the Pydantic model.  Splitting validation (here) from runtime
    use (Persona) means the runtime object is a hashable, frozen,
    cheap-to-pass record without Pydantic machinery on the hot path.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1)
    tools_allow: list[str] = Field(default_factory=list)
    max_iterations: int = Field(
        default=_DEFAULT_PERSONA_MAX_ITERATIONS,
        gt=0,
        le=PERSONA_MAX_ITERATIONS_CEILING,
    )
    max_wall_clock_seconds: float = Field(
        default=_DEFAULT_PERSONA_MAX_WALL_CLOCK_SECONDS,
        gt=0,
        le=PERSONA_MAX_WALL_CLOCK_CEILING_SECONDS,
    )
    default_reasoning_effort: ReasoningEffort | None = None

    @field_validator("tools_allow")
    @classmethod
    def _validate_tool_names(cls, v: list[str]) -> list[str]:
        """Reject unknown tool names.

        The cap chain elsewhere then narrows further; this is the static
        schema check.
        """
        unknown = [t for t in v if t not in KNOWN_TOOL_NAMES]
        if unknown:
            raise ValueError(
                f"tools_allow references unknown tool(s): {sorted(unknown)}. "
                f"Known tools: {sorted(KNOWN_TOOL_NAMES)}"
            )
        # De-dup while preserving order — frozen Persona stores a frozenset
        # but a stable serialised order helps debug.
        seen: set[str] = set()
        out: list[str] = []
        for t in v:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out


@dataclass(frozen=True)
class Persona:
    """Immutable runtime view of a persona.

    Built by :func:`_persona_from_spec` after the Pydantic spec has
    validated.  Kept frozen so callers can stash it in long-lived
    closures (the in-process spawn registry, the per-conversation
    persona cache) without worrying about mutation.
    """

    name: str
    description: str
    model: str
    tools_allow: frozenset[str]
    system_prompt: str
    max_iterations: int
    max_wall_clock_seconds: float
    default_reasoning_effort: ReasoningEffort | None
    #: Where the persona was loaded from — built-in dir or a workspace
    #: override path.  Useful for error messages and for the
    #: ``list_subagents`` tool to surface "researcher (workspace override)".
    source_path: Path


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _split_frontmatter(text: str, source: Path) -> tuple[str, str]:
    """Return ``(yaml_block, body)`` from a markdown file with YAML frontmatter.

    Raises :class:`PersonaError` when the fences are missing or the file
    is too short to be a real persona.  Strict on purpose — a silently
    half-parsed persona is worse than a noisy failure at boot.
    """
    lines = text.splitlines()
    if len(lines) < _MIN_PERSONA_LINES or lines[0].strip() != _FRONTMATTER_FENCE:
        raise PersonaError(
            f"{source}: missing opening '---' frontmatter fence; "
            f"file must start with YAML frontmatter."
        )
    try:
        close_idx = next(i for i in range(1, len(lines)) if lines[i].strip() == _FRONTMATTER_FENCE)
    except StopIteration as exc:
        raise PersonaError(f"{source}: missing closing '---' frontmatter fence.") from exc
    yaml_block = "\n".join(lines[1:close_idx])
    body = "\n".join(lines[close_idx + 1 :]).strip()
    if not body:
        raise PersonaError(f"{source}: persona body (system prompt) is empty.")
    return yaml_block, body


def _persona_from_spec(spec: _PersonaSpec, body: str, source: Path) -> Persona:
    """Build the runtime :class:`Persona` and validate the model id."""
    try:
        require_known(spec.model)
    except (InvalidModelId, UnknownModelId) as exc:
        # ``InvalidModelId`` fires when the string fails to parse (e.g.
        # "gpt-nonexistent"); ``UnknownModelId`` fires when it parses
        # but isn't a catalog entry (e.g. "google/gemini-9999-future").
        # Both surface as a single PersonaError so callers have one
        # exception type to catch.
        raise PersonaError(
            f"{source}: persona '{spec.name}' references model '{spec.model}' "
            f"which is not in MODEL_CATALOG. {exc}"
        ) from exc
    return Persona(
        name=spec.name,
        description=spec.description,
        model=spec.model,
        tools_allow=frozenset(spec.tools_allow),
        system_prompt=body,
        max_iterations=spec.max_iterations,
        max_wall_clock_seconds=spec.max_wall_clock_seconds,
        default_reasoning_effort=spec.default_reasoning_effort,
        source_path=source,
    )


def _parse_persona_file(path: Path) -> Persona:
    """Load + validate a single persona markdown file.

    Raises :class:`PersonaError` on any malformed input.  Pure function;
    no caching — the cache lives one layer up so workspace overrides
    can invalidate on mtime without touching this code.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PersonaError(f"{path}: failed to read persona file: {exc}") from exc

    yaml_block, body = _split_frontmatter(text, path)
    try:
        raw = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as exc:
        raise PersonaError(f"{path}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(raw, dict):
        raise PersonaError(f"{path}: frontmatter must be a YAML mapping, got {type(raw).__name__}.")

    try:
        spec = _PersonaSpec.model_validate(raw)
    except Exception as exc:
        # Pydantic's ValidationError prints rich detail.  Convert to
        # PersonaError so callers have one exception type to catch.
        raise PersonaError(f"{path}: schema validation failed: {exc}") from exc

    persona = _persona_from_spec(spec, body, path)
    if persona.name != path.stem:
        raise PersonaError(
            f"{path}: persona name '{persona.name}' must equal filename stem "
            f"'{path.stem}' so resolve_persona can find it by filename."
        )
    return persona


# ---------------------------------------------------------------------------
# Built-in loader (startup)
# ---------------------------------------------------------------------------


def load_builtin_personas(directory: Path | None = None) -> dict[str, Persona]:
    """Load every ``*.md`` persona in ``directory`` (default: built-in dir).

    Called once at FastAPI startup.  Re-raises :class:`PersonaError` so
    a broken built-in fails the app boot — the only place we want to
    discover schema drift.
    """
    target = directory or _BUILTIN_PERSONAS_DIR
    if not target.is_dir():
        _log.info("SUBAGENT_PERSONA_DIR_MISSING path=%s", target)
        return {}
    out: dict[str, Persona] = {}
    for md_path in sorted(target.glob("*.md")):
        persona = _parse_persona_file(md_path)
        if persona.name in out:
            raise PersonaError(
                f"{md_path}: duplicate persona name '{persona.name}' "
                f"(already loaded from {out[persona.name].source_path})."
            )
        out[persona.name] = persona
    _log.info(
        "SUBAGENT_BUILTIN_PERSONAS_LOADED count=%d names=%s",
        len(out),
        sorted(out.keys()),
    )
    return out


# ---------------------------------------------------------------------------
# Workspace override loader (per-spawn, mtime-cached)
# ---------------------------------------------------------------------------

# Per-workspace cache: workspace_root -> (mtime_signature, personas_dict).
# Mtime signature is the sum of (path, mtime_ns) for every .md file in the
# overrides dir; recomputed on every resolve so we notice file additions
# and removals — cheap stat() calls only.
_workspace_cache: dict[Path, tuple[tuple[tuple[str, int], ...], dict[str, Persona]]] = {}


def _workspace_overrides_dir(workspace_root: Path) -> Path:
    return workspace_root / _WORKSPACE_PERSONAS_SUBDIR


def _mtime_signature(directory: Path) -> tuple[tuple[str, int], ...]:
    """Return a stable signature of (path, mtime_ns) for every .md in dir."""
    if not directory.is_dir():
        return ()
    entries: list[tuple[str, int]] = []
    for p in sorted(directory.glob("*.md")):
        try:
            entries.append((p.name, p.stat().st_mtime_ns))
        except OSError:
            # File vanished between glob and stat — treat as absent.
            continue
    return tuple(entries)


def _load_workspace_personas_uncached(directory: Path) -> dict[str, Persona]:
    """Load overrides without consulting the cache.

    Workspace personas that fail validation are **skipped with a
    warning** rather than crashing the app — a single bad persona in a
    user's workspace must not break their chat.  The validation error
    is preserved on the warning log so the user can find it.
    """
    out: dict[str, Persona] = {}
    if not directory.is_dir():
        return out
    for md_path in sorted(directory.glob("*.md")):
        try:
            persona = _parse_persona_file(md_path)
        except PersonaError as exc:
            _log.warning("SUBAGENT_WORKSPACE_PERSONA_INVALID path=%s error=%s", md_path, exc)
            continue
        if persona.name in out:
            _log.warning(
                "SUBAGENT_WORKSPACE_PERSONA_DUPLICATE path=%s name=%s",
                md_path,
                persona.name,
            )
            continue
        out[persona.name] = persona
    return out


def load_workspace_personas(workspace_root: Path) -> dict[str, Persona]:
    """Return workspace persona overrides, refreshing the mtime cache.

    Cheap enough to call on every spawn — the hot path is a single
    glob + stat per .md file, no parse unless mtimes changed.
    """
    overrides_dir = _workspace_overrides_dir(workspace_root)
    signature = _mtime_signature(overrides_dir)
    cached = _workspace_cache.get(workspace_root)
    if cached is not None and cached[0] == signature:
        return cached[1]
    personas = _load_workspace_personas_uncached(overrides_dir)
    _workspace_cache[workspace_root] = (signature, personas)
    return personas


def clear_workspace_persona_cache() -> None:
    """Drop the per-workspace cache.

    Test-only — exposed so tests can force a re-read after writing fixtures.
    """
    _workspace_cache.clear()


# ---------------------------------------------------------------------------
# Resolver — the function the spawn tool calls
# ---------------------------------------------------------------------------


def resolve_persona(
    name: str,
    *,
    workspace_root: Path | None,
    builtin: dict[str, Persona],
) -> Persona:
    """Look up a persona by name with workspace overrides taking priority.

    Args:
        name: Persona name (matches the markdown filename stem).
        workspace_root: User's workspace; ``None`` skips the override
            lookup (e.g. for background jobs without a workspace).
        builtin: The dict returned by :func:`load_builtin_personas`,
            kept in app state at startup.  Passed in rather than
            re-loaded so each spawn doesn't re-glob the built-in dir.

    Raises:
        PersonaError: When no persona with ``name`` exists in either
            the workspace overrides or the built-in catalogue.
    """
    if workspace_root is not None:
        override = load_workspace_personas(workspace_root).get(name)
        if override is not None:
            return override
    persona = builtin.get(name)
    if persona is None:
        known = sorted(set(builtin.keys()))
        raise PersonaError(
            f"Unknown persona '{name}'. Known built-ins: {known}. "
            f"Workspace overrides live under '<workspace>/{_WORKSPACE_PERSONAS_SUBDIR}/'."
        )
    return persona


def list_builtin_personas(builtin: dict[str, Persona]) -> list[dict[str, str]]:
    """Return compact descriptors for the ``list_subagents`` tool preamble.

    Trims the system prompt — the parent model doesn't need it, only the
    description.
    """
    return [
        {"name": p.name, "description": p.description, "model": p.model}
        for p in sorted(builtin.values(), key=lambda x: x.name)
    ]
