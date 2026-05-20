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
    2. Scan ``.agent/skills/`` for subdirectories whose names do not
       start with ``_``.
    3. Merge each subdirectory with its manifest entry (if any) into a
       ``SkillEntry``, checking whether ``SKILL.md`` exists.
    4. Return up to ``_MAX_SKILLS`` entries sorted by name.

    Returns an empty list on any I/O error so the API degrades gracefully.
    """
    skills_dir = workspace_root / _SKILLS_DIR
    if not skills_dir.is_dir():
        return []

    manifest_lookup = _load_manifest(workspace_root)

    entries: list[SkillEntry] = []
    try:
        subdirs = sorted(
            (p for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith("_")),
            key=lambda p: p.name,
        )
    except OSError:
        log.warning("Failed to list skills directory: %s", skills_dir)
        return []

    for subdir in subdirs[:_MAX_SKILLS]:
        meta = manifest_lookup.get(subdir.name, {})
        entries.append(
            SkillEntry(
                name=subdir.name,
                trigger=meta.get("trigger", "—"),
                summary=meta.get("summary", "—"),
                has_skill_md=(subdir / _SKILL_MD_NAME).is_file(),
                extra={k: v for k, v in meta.items() if k not in ("name", "trigger", "summary")},
            )
        )

    return entries


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
