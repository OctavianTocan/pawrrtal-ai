"""Prompt framing and stdout parsing for ``agy --print``."""

from __future__ import annotations

import re
from typing import cast

AGY_FINAL_OPEN = "<pawrrtal_final>"
AGY_FINAL_CLOSE = "</pawrrtal_final>"
_FINAL_RE = re.compile(
    re.escape(AGY_FINAL_OPEN) + r"(.*?)" + re.escape(AGY_FINAL_CLOSE),
    re.DOTALL,
)
_HISTORY_PREFIX_MAX_ROWS = 20
_HISTORY_PREFIX_MAX_CHARS = 12_000


def build_framed_prompt(
    *,
    question: str,
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
) -> str:
    """Build a prompt that asks ``agy`` to wrap the final answer."""
    prefix = render_history_prefix(history, system_prompt)
    framing = (
        "Return your final user-visible answer inside exactly one "
        f"{AGY_FINAL_OPEN}...{AGY_FINAL_CLOSE} block. "
        "Answer directly without using tools unless the user explicitly asks you to inspect, "
        "modify, or execute something in the workspace. Do not put progress text inside the "
        "block.\n\n"
    )
    return framing + prefix + question


def extract_final_answer(stdout: str) -> str | None:
    """Return the last final-answer marker block from ``agy`` stdout."""
    matches = _FINAL_RE.findall(stdout)
    if not matches:
        return None
    return cast(str, matches[-1]).strip()


def is_timeout_output(stdout: str) -> bool:
    """Return whether stdout is the known ``agy --print`` timeout shape."""
    return "Error: timed out waiting for response" in stdout


def render_history_prefix(
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
) -> str:
    """Render bounded system and prior-turn context for a fresh CLI turn."""
    sections: list[str] = []
    sp = (system_prompt or "").strip()
    if sp:
        sections.append(_wrap_section("SYSTEM CONTEXT", _truncate_tail(sp)))
    rendered_history = _render_history_lines(history)
    if rendered_history:
        sections.append(_wrap_section("PRIOR CONVERSATION", _truncate_tail(rendered_history)))
    return "\n".join(sections)


def _wrap_section(label: str, body: str) -> str:
    return f"--- BEGIN {label} ---\n{body}\n--- END {label} ---\n"


def _truncate_tail(text: str) -> str:
    if len(text) <= _HISTORY_PREFIX_MAX_CHARS:
        return text
    return "..." + text[-_HISTORY_PREFIX_MAX_CHARS:]


def _render_history_lines(history: list[dict[str, str]] | None) -> str:
    if not history:
        return ""
    rows = [
        row
        for row in history[-_HISTORY_PREFIX_MAX_ROWS:]
        if row.get("role") in {"user", "assistant"} and (row.get("content") or "").strip()
    ]
    lines: list[str] = []
    for row in rows:
        speaker = "User" if row["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {(row.get('content') or '').strip()}")
    return "\n".join(lines)
