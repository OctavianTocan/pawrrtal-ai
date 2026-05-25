"""Conversation ID parsing for Antigravity CLI logs."""

from __future__ import annotations

import re

_CREATED_RE = re.compile(r"Created conversation (?P<id>[a-zA-Z0-9-]+)")
_RESUMED_RE = re.compile(r"resuming conversation (?P<id>[a-zA-Z0-9-]+)")


def parse_conversation_id(log_text: str) -> str | None:
    """Extract the latest Antigravity conversation ID from a log body."""
    for pattern in (_CREATED_RE, _RESUMED_RE):
        match = pattern.search(log_text)
        if match is not None:
            return match.group("id")
    return None
