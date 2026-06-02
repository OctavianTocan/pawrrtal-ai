"""Conversation ID parsing for Antigravity CLI logs."""

from __future__ import annotations

import re

_CONVERSATION_ID_RE = (
    r"(?P<id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
_CREATED_RE = re.compile(rf"Created conversation {_CONVERSATION_ID_RE}")
_RESUMED_RE = re.compile(rf"Print mode: resuming conversation {_CONVERSATION_ID_RE}")


def parse_conversation_id(log_text: str) -> str | None:
    """Extract the latest Antigravity conversation ID from a log body."""
    for pattern in (_CREATED_RE, _RESUMED_RE):
        match = pattern.search(log_text)
        if match is not None:
            return match.group("id")
    return None
