"""First-run persona bootstrap helpers for Paw workspaces."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.fs import read_capped_utf8

log = logging.getLogger(__name__)

BOOTSTRAP_FILENAME = "BOOTSTRAP.md"
BOOTSTRAP_STATE_PATH = ".pawrrtal/persona_bootstrap.json"
BOOTSTRAP_VERSION = 1

_MAX_BYTES = 32_000
_IDENTITY_PLACEHOLDER = "_(set a name for your agent)_"

BOOTSTRAP_TEMPLATE = """\
# BOOTSTRAP.md - First-Run Paw Setup

You are in persona bootstrap mode because this workspace does not yet have a
completed Paw identity.

Your underlying role is fixed: you are the user's Paw, their personal agent
inside Pawrrtal. "Paw" is the conceptual role. The user can choose your name,
voice, style, emoji, boundaries, and working preferences, and those can evolve
over time.

## What to do first

Ask one short first question, in your own words:

"I'm your Paw. What would you like to call me, and what kind of working style
should I have?"

Keep the setup conversational. Do not interrogate the user. If they give enough
information in one message, proceed. If they only give a name, ask one follow-up
about working style or boundaries.

## When enough information is available

Use the workspace file tools to update these files:

1. `IDENTITY.md` - name, vibe, optional emoji, and a short identity summary.
2. `SOUL.md` - durable operating identity and style. Keep the fixed Paw concept,
   but reflect the user's chosen name and personality.
3. `USER.md` - any durable user preferences or working conventions the user
   revealed during setup.
4. `.pawrrtal/persona_bootstrap.json` - write exactly:
   `{"version": 1, "completed": true}`

Do not say bootstrap is complete until those writes succeed. After completion,
answer normally on future turns.
"""


def seed_persona_bootstrap(root: Path) -> None:
    """Seed bootstrap files for a newly-created workspace."""
    (root / ".pawrrtal").mkdir(parents=True, exist_ok=True)
    if is_persona_bootstrap_completed(root):
        return
    bootstrap_path = root / BOOTSTRAP_FILENAME
    if not bootstrap_path.exists():
        bootstrap_path.write_text(BOOTSTRAP_TEMPLATE, encoding="utf-8")


def ensure_persona_bootstrap_seeded(root: Path) -> None:
    """Backfill bootstrap for existing untouched workspaces.

    Existing users may already have custom identity files. We only create
    ``BOOTSTRAP.md`` when the identity file is missing or still contains the
    original placeholder, which avoids re-running setup for a shaped Paw.
    """
    if is_persona_bootstrap_completed(root):
        return
    if (root / BOOTSTRAP_FILENAME).exists():
        return
    if _identity_needs_bootstrap(root):
        seed_persona_bootstrap(root)


def read_persona_bootstrap(root: Path) -> str | None:
    """Return bootstrap instructions when setup is pending."""
    if not is_persona_bootstrap_pending(root):
        return None
    return read_capped_utf8(root / BOOTSTRAP_FILENAME, max_bytes=_MAX_BYTES)


def is_persona_bootstrap_pending(root: Path) -> bool:
    """Return whether the workspace should include bootstrap instructions."""
    return (root / BOOTSTRAP_FILENAME).exists() and not is_persona_bootstrap_completed(root)


def is_persona_bootstrap_completed(root: Path) -> bool:
    """Return whether the bootstrap marker says setup is complete."""
    state_path = root / BOOTSTRAP_STATE_PATH
    if not state_path.exists():
        return False
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("PERSONA_BOOTSTRAP_STATE_INVALID path=%s error=%s", state_path, exc)
        return False
    return (
        isinstance(payload, dict)
        and payload.get("version") == BOOTSTRAP_VERSION
        and payload.get("completed") is True
    )


def _identity_needs_bootstrap(root: Path) -> bool:
    identity = read_capped_utf8(root / "IDENTITY.md", max_bytes=_MAX_BYTES)
    if identity is None:
        return True
    return _IDENTITY_PLACEHOLDER in identity
