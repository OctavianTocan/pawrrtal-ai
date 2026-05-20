"""Workspace management service.

A workspace is an agentic-stack-compatible agent home directory. Each
user can have multiple workspaces; each workspace is a self-contained
tree at ``{workspace_base_dir}/{uuid}/`` whose entire agent surface
lives under ``.agent/`` — the canonical layout from
https://github.com/codejunkie99/agentic-stack.

Standard file layout::

    {workspace_root}/
    └── .agent/                              # agentic-stack canonical brain
        ├── AGENTS.md                        # operating contract (upstream)
        ├── HEARTBEAT.md                     # Paw heartbeat schedule (overlay)
        ├── state/                           # bootstrap markers etc. (overlay)
        ├── memory/                          # personal/working/episodic/semantic/candidates
        │   └── personal/PREFERENCES.md      # overlay: identity JSON block + user profile
        ├── skills/                          # 10 upstream skills + paw-persona + paw-bootstrap
        ├── protocols/                       # permissions.md, delegation.md, hook_patterns.json
        ├── harness/                         # hooks + conductor (upstream)
        └── tools/                           # CLI utilities (upstream)

Seeding is two ``copytree`` calls + a one-time PREFERENCES.md render
+ an append into the upstream skill registry. The agentic-stack
template lives at ``vendor/agentic-stack/`` (git submodule); the Paw
overlay lives at ``backend/templates/paw-overlay/``. Updating
upstream: ``git submodule update --remote vendor/agentic-stack``.
Updating Paw bits: edit the overlay files directly — no Python
changes needed for content edits.

Idempotent: re-running ``seed_workspace`` skips files that already
exist (so agent-authored memory and skills survive) and only appends
to the skill registry if the Paw entries aren't there yet.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import settings

log = logging.getLogger(__name__)

PAW_MANIFEST_ENTRIES_FILENAME = "_paw_manifest_entries.jsonl"
PAW_INDEX_ENTRIES_FILENAME = "_paw_index_entries.md"


@runtime_checkable
class PersonalizationFields(Protocol):
    """Subset of ``UserPersonalization`` attributes the workspace seeder reads.

    Declared here (in ``app.core``) so the seeder stays in the architectural
    core layer without importing from ``app.models`` — that import would
    invert the sentrux layer ordering (``be-core`` must not depend on
    ``be-models``). Any ORM instance with matching attributes — notably
    ``UserPersonalization`` — satisfies this protocol via duck typing, so
    callers in higher layers can keep passing the model directly.
    """

    name: str | None
    role: str | None
    company_website: str | None
    linkedin: str | None
    goals: list[str] | None
    personality: str | None
    custom_instructions: str | None


def _workspace_path(workspace_id: uuid.UUID) -> Path:
    """Return the absolute path for a workspace directory."""
    return Path(settings.workspace_base_dir) / str(workspace_id)


def _agentic_stack_src() -> Path:
    """Return the agentic-stack template root (contains ``.agent/``)."""
    return Path(settings.agentic_stack_template_dir)


def _paw_overlay_src() -> Path:
    """Return the Paw overlay root (contains ``.agent/`` mirroring destination)."""
    return Path(settings.paw_overlay_template_dir)


def seed_workspace(
    workspace_id: uuid.UUID,
    personalization: PersonalizationFields | None = None,
    *,
    path: Path | None = None,
) -> Path:
    """Create the workspace directory tree and seed its files.

    Idempotent — existing files are not overwritten, so re-running after
    a partial seed is safe and agent-authored content is preserved.

    Pass ``path`` to override the default ``{workspace_base_dir}/{uuid}``
    location with a caller-supplied root (used by the dev-admin shortcut
    so its workspace folder stays stable across DB resets).

    Returns the workspace root path.
    """
    root = path if path is not None else _workspace_path(workspace_id)
    root.mkdir(parents=True, exist_ok=True)

    agentic_src = _agentic_stack_src() / ".agent"
    overlay_src = _paw_overlay_src() / ".agent"

    if not agentic_src.is_dir():
        raise FileNotFoundError(
            f"agentic-stack template missing at {agentic_src}. "
            "Did you run `git submodule update --init --recursive`?"
        )

    # 1. Lay down the canonical agentic-stack `.agent/` tree.
    _copy_tree_skip_existing(agentic_src, root / ".agent")

    # 2. Layer the Paw overlay (HEARTBEAT.md, paw-persona, paw-bootstrap,
    #    PREFERENCES.md placeholder) — also skip-existing so user edits
    #    survive on re-seed.
    if overlay_src.is_dir():
        _copy_tree_skip_existing(overlay_src, root / ".agent")

    # 3. Render PREFERENCES.md with personalization data on first seed only.
    _render_preferences_on_first_seed(root, personalization)

    # 4. Append Paw skills to the upstream skill registry (idempotent).
    _register_paw_skills(root)

    return root


def _copy_tree_skip_existing(src: Path, dst: Path) -> None:
    """Recursively copy ``src`` into ``dst``; never overwrite existing files.

    ``shutil.copytree(..., dirs_exist_ok=True)`` would overwrite — that's
    wrong for re-seeding workspaces whose memory and skills the agent
    has been editing. This helper preserves whatever the destination
    already has and only copies files that are missing.
    """
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dst / entry.name
        if entry.is_dir():
            _copy_tree_skip_existing(entry, target)
        elif not target.exists():
            shutil.copy2(entry, target)


def _render_preferences_on_first_seed(
    root: Path,
    personalization: PersonalizationFields | None,
) -> None:
    """Render the Paw-flavored PREFERENCES.md on first seed.

    The agentic-stack template ships its own stub PREFERENCES.md that
    the copytree step lays down first. We replace it with the Paw
    template (identity JSON block + personalization data) **only** when
    the file is still byte-identical to the upstream stub — i.e. no
    one has touched it. Once the agent, user, or an earlier seed has
    edited PREFERENCES.md (including the Paw render itself, which
    introduces the identity marker), the file diverges from the stub
    and this function is a no-op so the existing content survives
    every re-seed.
    """
    target = root / ".agent" / "memory" / "personal" / "PREFERENCES.md"
    agentic_stub = _agentic_stack_src() / ".agent" / "memory" / "personal" / "PREFERENCES.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(_build_preferences_md(personalization), encoding="utf-8")
        return
    if not agentic_stub.exists():
        return
    try:
        existing = target.read_text(encoding="utf-8")
        stub = agentic_stub.read_text(encoding="utf-8")
    except OSError:
        log.warning("PREFERENCES_RENDER_READ_FAILED path=%s", target, exc_info=True)
        return
    if existing == stub:
        target.write_text(_build_preferences_md(personalization), encoding="utf-8")


def _build_preferences_md(personalization: PersonalizationFields | None) -> str:
    """Render PREFERENCES.md content with the identity JSON block + user profile.

    The identity block sits between HTML comment markers so
    ``persona_bootstrap`` can locate and rewrite it. The block stays
    valid one-line JSON.
    """
    identity_block = '{"name": null, "vibe": null, "emoji": null, "bootstrap_completed": false}'

    lines: list[str] = [
        "# Personal Preferences",
        "",
        "> This is your Paw's home for who you are and how you work.",
        "> The identity block below is machine-readable; your Paw updates",
        "> it during first-run setup. Edit the freeform sections freely.",
        "",
        "## Identity",
        "",
        "<!-- pawrrtal:identity:begin -->",
        identity_block,
        "<!-- pawrrtal:identity:end -->",
        "",
        "## About you",
        "",
    ]

    if personalization is None or not _has_personalization_data(personalization):
        lines.append("_(Your Paw will fill this in during first-run setup.)_")
    else:
        _append_personalization_lines(lines, personalization)

    lines.extend(
        [
            "",
            "## Code style",
            "",
            "- _(your Paw will record standing preferences here as you state them)_",
            "",
            "## Workflow",
            "",
            "- _(your Paw will record workflow preferences here as you state them)_",
            "",
            "## Communication",
            "",
            "- _(your Paw will record communication preferences here as you state them)_",
            "",
        ]
    )
    return "\n".join(lines)


def _has_personalization_data(personalization: PersonalizationFields) -> bool:
    """Return True when at least one personalization field has content."""
    return any(
        (
            personalization.name,
            personalization.role,
            personalization.company_website,
            personalization.linkedin,
            personalization.goals,
            personalization.custom_instructions,
        )
    )


def _append_personalization_lines(
    lines: list[str], personalization: PersonalizationFields
) -> None:
    """Append the ``About you`` bullets and ``Custom instructions`` block."""
    if personalization.name:
        lines.append(f"- **Name:** {personalization.name}")
    if personalization.role:
        lines.append(f"- **Role:** {personalization.role}")
    if personalization.company_website:
        lines.append(f"- **Company / Website:** {personalization.company_website}")
    if personalization.linkedin:
        lines.append(f"- **LinkedIn:** {personalization.linkedin}")
    if personalization.goals:
        goals = personalization.goals
        rendered = ", ".join(goals) if isinstance(goals, list) else str(goals)
        lines.append(f"- **Goals:** {rendered}")
    if personalization.custom_instructions:
        lines.extend(["", "## Custom instructions", "", personalization.custom_instructions])


def _register_paw_skills(root: Path) -> None:
    """Append paw-persona and paw-bootstrap entries to upstream skill registries.

    Idempotent: skips entries already present in either file. The
    entries themselves live as overlay artifacts
    (``_paw_manifest_entries.jsonl`` and ``_paw_index_entries.md``) so
    updating them is a Markdown/JSONL edit, not a Python change.
    """
    skills_dir = root / ".agent" / "skills"
    manifest_path = skills_dir / "_manifest.jsonl"
    index_path = skills_dir / "_index.md"
    overlay_manifest = (
        _paw_overlay_src() / ".agent" / "skills" / PAW_MANIFEST_ENTRIES_FILENAME
    )
    overlay_index = _paw_overlay_src() / ".agent" / "skills" / PAW_INDEX_ENTRIES_FILENAME

    _append_paw_manifest_entries(manifest_path, overlay_manifest)
    _append_paw_index_entries(index_path, overlay_index)

    # The overlay copy carries the entry files into the workspace's
    # skills dir; remove them so they don't confuse skill discovery
    # (which treats any non-underscore directory as a skill).
    for stray in (skills_dir / PAW_MANIFEST_ENTRIES_FILENAME, skills_dir / PAW_INDEX_ENTRIES_FILENAME):
        if stray.exists():
            stray.unlink()


def _append_paw_manifest_entries(manifest_path: Path, overlay_manifest: Path) -> None:
    if not overlay_manifest.exists() or not manifest_path.exists():
        return
    existing = manifest_path.read_text(encoding="utf-8")
    new_lines = [
        line for line in overlay_manifest.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    additions = [line for line in new_lines if line not in existing]
    if not additions:
        return
    suffix = "" if existing.endswith("\n") or not existing else "\n"
    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(suffix + "\n".join(additions) + "\n")


def _append_paw_index_entries(index_path: Path, overlay_index: Path) -> None:
    if not overlay_index.exists() or not index_path.exists():
        return
    existing = index_path.read_text(encoding="utf-8")
    addition = overlay_index.read_text(encoding="utf-8").strip()
    if not addition or "## paw-persona" in existing or "## paw-bootstrap" in existing:
        return
    suffix = "" if existing.endswith("\n") else "\n"
    with index_path.open("a", encoding="utf-8") as fh:
        fh.write(suffix + "\n" + addition + "\n")
