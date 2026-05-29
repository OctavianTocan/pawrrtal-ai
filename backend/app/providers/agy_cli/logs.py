"""Structured logging helpers for Antigravity CLI log files."""

from __future__ import annotations

import re
from typing import TypedDict


class AgyLogEvent(TypedDict):
    """Event summary classified from an Antigravity CLI log line."""

    event: str
    summary: str


# Regex matching model selection, auto-approvals, and conversation lifecycles.
_MODEL_RE = re.compile(r'label="(?P<label>[^"]+)"')
_TOOL_CONFIRM_RE = re.compile(r'Auto-approving tool confirmation: "(?P<tool>[^"]+)"')
_CREATED_RE = re.compile(r"Created conversation (?P<id>[a-zA-Z0-9-]+)")
_RESUMED_RE = re.compile(r"resuming conversation (?P<id>[a-zA-Z0-9-]+)")


def classify_log_line(line: str) -> AgyLogEvent | None:
    """Classify a known ``agy`` log line into a stable structured event."""
    if "Propagating selected model override" in line:
        match = _MODEL_RE.search(line)
        return {"event": "model_selected", "summary": match.group("label") if match else "unknown"}
    if "Auto-approving tool confirmation" in line:
        match = _TOOL_CONFIRM_RE.search(line)
        return {
            "event": "tool_permission_auto_approved",
            "summary": match.group("tool") if match else "unknown",
        }
    created = _CREATED_RE.search(line)
    if created:
        return {"event": "conversation_created", "summary": created.group("id")}
    resumed = _RESUMED_RE.search(line)
    if resumed:
        return {"event": "conversation_resumed", "summary": resumed.group("id")}
    if "timed out" in line:
        return {"event": "timeout", "summary": "print mode timed out"}
    return None
