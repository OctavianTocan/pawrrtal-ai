"""Workspace management service.

Each workspace is a Pawrrtal-owned agent home at
``{workspace_base_dir}/{uuid}/``. User-facing context files live at the
workspace root; internal agent assets live under ``.agent/``.

Standard file layout::

    {workspace_root}/
    ├── .env
    ├── AGENTS.md
    ├── CLAUDE.md -> AGENTS.md
    ├── HEARTBEAT.md
    ├── PREFERENCES.md
    ├── SOUL.md
    ├── USER.md
    ├── .agents/skills -> ../.agent/skills
    ├── .claude/skills -> ../.agent/skills
    └── .agent/
        ├── memory/
        ├── protocols/
        ├── harness/
        ├── tools/
        └── skills/

Idempotent: re-running ``seed_workspace`` skips files that already
exist, so agent-authored memory, skills, and user edits survive.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.core.keys import save_workspace_env

log = logging.getLogger(__name__)

PREFERENCES_FILENAME = "PREFERENCES.md"
WORKSPACE_ENV_FILENAME = ".env"

_SYMLINKS: tuple[tuple[str, str], ...] = (
    ("CLAUDE.md", "AGENTS.md"),
    (".agents/skills", "../.agent/skills"),
    (".claude/skills", "../.agent/skills"),
)


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


def _workspace_template_src() -> Path:
    """Return the Pawrrtal-owned workspace template root."""
    return Path(settings.workspace_template_dir)


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

    template_src = _workspace_template_src()
    if not template_src.is_dir():
        raise FileNotFoundError(
            f"workspace template missing at {template_src}. "
            "Expected backend/templates/workspace to be present."
        )

    preferences_existed = _path_exists(root / PREFERENCES_FILENAME)
    env_existed = _path_exists(root / WORKSPACE_ENV_FILENAME)
    _copy_tree_skip_existing(template_src, root)
    if not preferences_existed:
        _write_preferences(root, personalization)
    if not env_existed:
        save_workspace_env(root, {})
    _ensure_required_symlinks(root)

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
            _seed_directory_entry(entry, target)
            continue

        # File entry — skip if target already exists (preserve agent edits).
        if not _path_exists(target):
            shutil.copy2(entry, target)
            continue

        if target.is_dir():
            raise FileExistsError(f"Cannot seed file {entry} over existing directory {target}")


def _seed_directory_entry(entry: Path, target: Path) -> None:
    """Validate and recurse into a directory entry during workspace seeding."""
    if _path_exists(target) and not target.is_dir():
        raise FileExistsError(f"Cannot seed directory {entry} over existing non-directory {target}")
    _copy_tree_skip_existing(entry, target)


def _path_exists(path: Path) -> bool:
    """Return True for real paths and symlinks, including broken symlinks."""
    return os.path.lexists(path)


def _write_preferences(
    root: Path,
    personalization: PersonalizationFields | None,
) -> None:
    """Render the root-level PREFERENCES.md on first seed."""
    target = root / PREFERENCES_FILENAME
    target.write_text(_build_preferences_md(personalization), encoding="utf-8")


def _ensure_required_symlinks(root: Path) -> None:
    """Create required compatibility symlinks without accepting real conflicts."""
    for link_name, target_name in _SYMLINKS:
        _ensure_symlink(root / link_name, target_name)


def _ensure_symlink(link_path: Path, target_name: str) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink():
        existing_target = link_path.readlink()
        if existing_target == Path(target_name):
            return
        raise FileExistsError(
            f"Symlink {link_path} points to {existing_target!r}, expected {target_name!r}"
        )
    if _path_exists(link_path):
        raise FileExistsError(
            f"Cannot create symlink {link_path} -> {target_name}: path already exists"
        )
    try:
        link_path.symlink_to(target_name)
    except OSError:
        log.warning(
            "WORKSPACE_SYMLINK_CREATE_FAILED path=%s target=%s",
            link_path,
            target_name,
            exc_info=True,
        )
        raise


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


def _append_personalization_lines(lines: list[str], personalization: PersonalizationFields) -> None:
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
