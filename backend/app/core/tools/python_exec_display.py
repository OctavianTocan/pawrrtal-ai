"""Display helpers for the ``python`` agent tool.

Pulled out of :mod:`app.core.tools.python_exec` so that module stays
under the project's 500-line file budget (enforced by
``scripts/check-file-lines.mjs``). Closes part of #302.

Two helpers + two constants:

* :data:`_PREVIEW_MAX_CHARS` / :func:`python_code_preview` — one-line
  source summary surfaced in ``ToolDisplayPayload.present`` /
  ``compact`` so Telegram and the web chain-of-thought no longer show
  bare ``(code)``.
* :data:`_DETAIL_MAX_CHARS` / :func:`python_code_detail` — full,
  head-truncated source rendered as a fenced code block in the
  payload's ``detail`` field for the expandable view.
"""

from __future__ import annotations

_PREVIEW_MAX_CHARS = 80
_DETAIL_MAX_CHARS = 1500


def python_code_preview(code: object) -> str:
    """Return a one-line summary of *code* for inline tool-trace rendering.

    Returns the first non-blank line of source, truncated to
    :data:`_PREVIEW_MAX_CHARS`. ``(empty)`` when nothing was supplied —
    the model occasionally calls the tool with an empty body and the
    fallback string keeps the trace readable.
    """
    text = str(code or "").strip()
    if not text:
        return "(empty)"
    first_line = next((line for line in text.splitlines() if line.strip()), text)
    if len(first_line) > _PREVIEW_MAX_CHARS:
        return f"{first_line[: _PREVIEW_MAX_CHARS - 1]}…"
    return first_line


def python_code_detail(code: object) -> str | None:
    """Return a fenced-block detail rendering of *code* for the chain-of-thought view.

    Truncates past :data:`_DETAIL_MAX_CHARS` so a runaway prompt
    doesn't push out the rest of the trace. ``None`` when the model
    didn't supply any code (the inline ``present`` field already
    covers the empty case).
    """
    text = str(code or "").rstrip()
    if not text.strip():
        return None
    if len(text) > _DETAIL_MAX_CHARS:
        text = f"{text[: _DETAIL_MAX_CHARS - 1]}…"
    return f"```python\n{text}\n```"
