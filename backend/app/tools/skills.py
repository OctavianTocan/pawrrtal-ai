"""Skill manifest reader for the workspace API layer.

Reads ``.agent/skills/_manifest.jsonl`` for machine-readable skill
metadata and falls back to directory discovery when the manifest is
absent or corrupt.

No database access, no network calls — pure filesystem reads.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.infrastructure.config import settings

log = logging.getLogger(__name__)

_SKILLS_DIR = ".agent/skills"
_MANIFEST_FILE = ".agent/skills/_manifest.jsonl"
_SKILL_MD_NAME = "SKILL.md"

# Hard caps to prevent runaway directory scanning or line parsing.
_MAX_SKILLS = 200
_MAX_MANIFEST_LINE_BYTES = 4_000


@dataclass
class SkillEntry:
    """A single skill discovered in the workspace skills directory."""

    name: str
    trigger: str
    summary: str
    has_skill_md: bool
    extra: dict[str, Any] = field(default_factory=dict)


def read_skill_manifest(workspace_root: Path) -> list[SkillEntry]:
    """Return all skills found in the workspace skills directory.

    Strategy:
    1. Parse ``.agent/skills/_manifest.jsonl`` line-by-line into a
       name → dict lookup. Corrupt lines are skipped with a warning;
       the function never raises.
    2. If the manifest has at least one valid entry, treat it as the
       authoritative allowlist. This keeps copied or backup skill
       folders from leaking into the agent prompt.
    3. If the manifest is absent, empty, or fully invalid, fall back to
       directory discovery for backwards compatibility.
    4. Return up to ``_MAX_SKILLS`` public entries sorted by name.

    Returns an empty list on any I/O error so the API degrades gracefully.
    """
    skills_dir = workspace_root / _SKILLS_DIR
    if not skills_dir.is_dir():
        return []

    manifest_lookup = _load_manifest(workspace_root)
    if manifest_lookup and _looks_like_legacy_manifest(manifest_lookup):
        template_lookup = _load_manifest(Path(settings.workspace_template_dir))
        if template_lookup:
            manifest_lookup = template_lookup

    entries: list[SkillEntry] = []
    if manifest_lookup:
        for name in sorted(manifest_lookup)[:_MAX_SKILLS]:
            if not _is_public_skill_name(name):
                continue
            meta = manifest_lookup[name]
            skill_dir = skills_dir / name
            entries.append(_entry_from_meta(name=name, skill_dir=skill_dir, meta=meta))
        return entries

    try:
        subdirs = sorted(
            (p for p in skills_dir.iterdir() if p.is_dir() and _is_public_skill_name(p.name)),
            key=lambda p: p.name,
        )
    except OSError:
        log.warning("Failed to list skills directory: %s", skills_dir)
        return []

    entries.extend(
        _entry_from_meta(name=subdir.name, skill_dir=subdir, meta={})
        for subdir in subdirs[:_MAX_SKILLS]
    )

    return entries


def _is_public_skill_name(name: str) -> bool:
    """Return whether ``name`` may be exposed as a workspace skill."""
    return bool(name) and not name.startswith(("_", "."))


def _entry_from_meta(
    *,
    name: str,
    skill_dir: Path,
    meta: dict[str, Any],
) -> SkillEntry:
    """Build a :class:`SkillEntry` for a manifest name or discovered dir."""
    return SkillEntry(
        name=name,
        trigger=meta.get("trigger", "—"),
        summary=meta.get("summary", "—"),
        has_skill_md=(skill_dir / _SKILL_MD_NAME).is_file(),
        extra={k: v for k, v in meta.items() if k not in ("name", "trigger", "summary")},
    )


def _load_manifest(workspace_root: Path) -> dict[str, dict[str, Any]]:
    """Parse ``.agent/skills/_manifest.jsonl`` into a name → metadata dict.

    Skips lines that exceed ``_MAX_MANIFEST_LINE_BYTES`` or fail JSON parsing.
    Returns an empty dict if the file is absent or unreadable.
    """
    manifest_path = workspace_root / _MANIFEST_FILE
    if not manifest_path.is_file():
        return {}

    lookup: dict[str, dict[str, Any]] = {}
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError:
        log.warning("Could not read skill manifest: %s", manifest_path)
        return {}

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if len(line.encode()) > _MAX_MANIFEST_LINE_BYTES:
            log.warning("Skill manifest line %d exceeds byte limit, skipping", lineno)
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            log.warning("Skill manifest line %d is not valid JSON, skipping", lineno)
            continue
        if not isinstance(entry, dict):
            log.warning("Skill manifest line %d is not a JSON object, skipping", lineno)
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            lookup[name] = entry

    return lookup


def _looks_like_legacy_manifest(manifest_lookup: dict[str, dict[str, Any]]) -> bool:
    """Return whether a manifest is an old copied skill inventory."""
    if any(_has_nonempty_summary(entry) for entry in manifest_lookup.values()):
        return False
    return any(
        isinstance(entry.get("triggers"), list)
        or isinstance(entry.get("tools"), list)
        or isinstance(entry.get("category"), str)
        or isinstance(entry.get("location"), str)
        for entry in manifest_lookup.values()
    )


def _has_nonempty_summary(entry: dict[str, Any]) -> bool:
    """Return whether a manifest entry has Pawrrtal display metadata."""
    summary = entry.get("summary")
    return isinstance(summary, str) and bool(summary.strip())
