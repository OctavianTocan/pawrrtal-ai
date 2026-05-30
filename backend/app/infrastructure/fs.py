"""Small filesystem utilities shared across the backend.

Lives at ``app.infrastructure.fs`` so it can be imported from anywhere — tool
modules, route handlers, CRUD helpers — without dragging in a tool's
domain (e.g. ``agents_md``) just to reuse the file-read primitive.

Each helper is intentionally small, side-effect free, and does its own
guarding so callers don't have to wrap each call in try/except.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def read_capped_utf8(target: Path, *, max_bytes: int) -> str | None:
    """Read *target* as UTF-8 with size + encoding guards.

    Returns the stripped text, or ``None`` when the file is missing,
    unreadable, exceeds *max_bytes* and decodes to nothing useful, or
    is empty after stripping.

    Files larger than *max_bytes* are silently truncated to that limit
    before decoding (with a warning log) — the caller's contract is
    "give me at most this much text", which is what most "read an
    optional config/identity file" sites actually want.

    Used by:
      - ``app.tools.agents_md`` (SOUL.md / AGENTS.md loader)
      - any future site that needs to read a small, possibly-missing
        text file without writing the same try/except dance.

    Not used by ``workspace_files.read_file`` because that tool has
    different semantics — it must surface decode failures to the
    model as a structured ``ToolError(BINARY_FILE)`` instead of
    swallowing them as ``None``.
    """
    if not target.is_file():
        log.debug("read_capped_utf8: %s not found", target)
        return None
    try:
        raw = target.read_bytes()
    except OSError as exc:
        log.warning("read_capped_utf8: cannot read %s: %s", target, exc)
        return None
    if len(raw) > max_bytes:
        log.warning(
            "read_capped_utf8: %s exceeds %d bytes, truncating",
            target,
            max_bytes,
        )
        raw = raw[:max_bytes]
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        log.warning("read_capped_utf8: %s is not valid UTF-8", target)
        return None
    return text or None
