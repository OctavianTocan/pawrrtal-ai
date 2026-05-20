"""First-run persona bootstrap helpers for Paw workspaces.

The Paw's identity (name, vibe, emoji, bootstrap-completion flag) lives
as a single-line JSON block inside the workspace's
``.agent/memory/personal/PREFERENCES.md`` file, between the marker
comments:

    <!-- pawrrtal:identity:begin -->
    {"name": null, "vibe": null, "emoji": null, "bootstrap_completed": false}
    <!-- pawrrtal:identity:end -->

When ``bootstrap_completed`` is false, the system prompt assembler
includes the body of ``.agent/skills/paw-bootstrap/SKILL.md`` so the
agent runs the first-run conversation. Once the agent flips the flag
to true the bootstrap skill stops being injected.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.core.fs import read_capped_utf8

log = logging.getLogger(__name__)

PREFERENCES_PATH = ".agent/memory/personal/PREFERENCES.md"
BOOTSTRAP_SKILL_PATH = ".agent/skills/paw-bootstrap/SKILL.md"
IDENTITY_BEGIN = "<!-- pawrrtal:identity:begin -->"
IDENTITY_END = "<!-- pawrrtal:identity:end -->"

_MAX_BYTES = 32_000
_IDENTITY_BLOCK_PATTERN = re.compile(
    re.escape(IDENTITY_BEGIN) + r"\s*(.+?)\s*" + re.escape(IDENTITY_END),
    re.DOTALL,
)


def read_persona_bootstrap(root: Path) -> str | None:
    """Return the paw-bootstrap skill body when first-run setup is pending."""
    if not is_persona_bootstrap_pending(root):
        return None
    return read_capped_utf8(root / BOOTSTRAP_SKILL_PATH, max_bytes=_MAX_BYTES)


def is_persona_bootstrap_pending(root: Path) -> bool:
    """Return True when the bootstrap skill should be injected this turn."""
    if not (root / BOOTSTRAP_SKILL_PATH).exists():
        return False
    return not is_persona_bootstrap_completed(root)


def is_persona_bootstrap_completed(root: Path) -> bool:
    """Return True when the identity block has ``bootstrap_completed: true``.

    Returns False (i.e. "still pending") when the file is missing or the
    JSON block is malformed — failure modes route the user back through
    setup rather than skipping it silently.
    """
    identity = _read_identity_block(root)
    if identity is None:
        return False
    return identity.get("bootstrap_completed") is True


def _read_identity_block(root: Path) -> dict[str, object] | None:
    """Extract the JSON identity block from PREFERENCES.md."""
    text = read_capped_utf8(root / PREFERENCES_PATH, max_bytes=_MAX_BYTES)
    if text is None:
        return None
    match = _IDENTITY_BLOCK_PATTERN.search(text)
    if match is None:
        log.warning("IDENTITY_BLOCK_MISSING path=%s", root / PREFERENCES_PATH)
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        log.warning(
            "IDENTITY_BLOCK_INVALID path=%s error=%s", root / PREFERENCES_PATH, exc
        )
        return None
    if not isinstance(payload, dict):
        log.warning("IDENTITY_BLOCK_NOT_OBJECT path=%s", root / PREFERENCES_PATH)
        return None
    return payload
