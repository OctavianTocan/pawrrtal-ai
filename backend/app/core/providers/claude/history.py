"""Bounded prior-turn recap for cross-provider conversation continuity.

When the user switches providers mid-conversation, the Claude SDK has
no transcript for the app-level ``conversation_id`` yet — but the app
does. Replaying it as a system-prompt addendum lets the model see the
prior turns instead of starting blind. Closes #308.

This module is the home for that rendering logic; it has no Claude
SDK or provider state and is trivially unit-testable in isolation.
"""

from __future__ import annotations

# How many of the most recent rows from ``history`` we surface to the
# model on a cold provider switch. The chat router caps ``history_window``
# to 20 already, but the LCM path can balloon this list — bound it again
# here so a giant history can't poison the first Claude turn.
_HISTORY_PREFIX_MAX_ROWS = 20

# Hard cap on the rendered prefix length. Long histories get truncated
# at the head (oldest first) so the most recent turns are always preserved.
_HISTORY_PREFIX_MAX_CHARS = 12_000


def _render_history_prefix(history: list[dict[str, str]] | None) -> str | None:
    """Render prior turns as a bounded recap the model can read.

    Returns ``None`` when ``history`` is empty or carries no usable
    ``user``/``assistant`` rows. The output is wrapped in clear
    BEGIN/END markers so the model never confuses it with the user's
    actual current message.

    Closes #308.
    """
    if not history:
        return None
    rows = [
        row
        for row in history[-_HISTORY_PREFIX_MAX_ROWS:]
        if row.get("role") in {"user", "assistant"} and (row.get("content") or "").strip()
    ]
    if not rows:
        return None
    lines = ["(Conversation context — earlier turns from this same conversation:)"]
    for row in rows:
        speaker = "User" if row["role"] == "user" else "Assistant"
        content = (row.get("content") or "").strip()
        lines.append(f"{speaker}: {content}")
    body = "\n".join(lines)
    if len(body) > _HISTORY_PREFIX_MAX_CHARS:
        body = "…" + body[-_HISTORY_PREFIX_MAX_CHARS:]
    return f"--- BEGIN PRIOR CONTEXT ---\n{body}\n--- END PRIOR CONTEXT ---"
