"""Gemini ``ThinkingConfig`` composer + safe-default lookup table.

Split out of ``gemini_provider`` to keep that module under the
project's 500-line file budget. ``include_thoughts=True`` is sent on
every request; ``thinking_level`` is the per-turn knob that maps from
Pawrrtal's five-level :class:`~.base.ReasoningEffort` literal onto
Gemini 3's four-level ``thinking_level`` enum
(``minimal | low | medium | high``).

The safe-default lookup table exists because Gemini 3 series models
default to ``thinking_level=high`` upstream, which counts thinking
tokens against ``maxOutputTokens``. On tool follow-up turns the model
routinely exhausts that budget on internal reasoning and returns
`stop_reason=stop` with an empty text part — the
``TELEGRAM_TOOL_ONLY_TURN`` empty-bubble bug. We pin per-model
defaults so an unconfigured chat turn stays interactive; users who
want deeper reasoning opt in via ``/thinking``.
"""

from __future__ import annotations

from google.genai import types as gtypes

from app.core.providers.base import ReasoningEffort

# Map Pawrrtal's five-level ``ReasoningEffort`` literal onto Gemini 3's
# four-level ``thinking_level`` enum. ``extra-high`` saturates at
# ``high`` because Gemini 3 caps its dynamic thinking budget there
# (see the Gemini 3 developer guide).
_GEMINI_THINKING_LEVEL: dict[str, str] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "extra-high": "high",
}

# Per-model fallback when the chat router didn't pass an explicit
# ``reasoning_effort``. Mirrors the per-model defaults documented in
# https://ai.google.dev/gemini-api/docs/gemini-3 but shifts the
# heavier-by-default models down one notch so an unconfigured chat
# turn stays interactive. Lookup is by substring on the canonical
# model slug; anything not matched falls back to
# :data:`_GEMINI_DEFAULT_THINKING_LEVEL`.
_GEMINI_PER_MODEL_DEFAULT_LEVEL: tuple[tuple[str, str], ...] = (
    ("flash-lite", "minimal"),  # Flash-Lite already defaults to minimal upstream
    ("3.5-flash", "low"),  # 3.5 Flash defaults to medium; trim for chat throughput
    ("3-flash", "low"),  # Gemini 3 Flash preview defaults to high (dynamic)
    ("3.1-pro", "medium"),  # Pro is the heaviest model; medium balances reasoning vs cost
)
_GEMINI_DEFAULT_THINKING_LEVEL = "low"


def default_thinking_level_for(model_id: str) -> str:
    """Return the safe-default ``thinking_level`` for ``model_id``."""
    for needle, level in _GEMINI_PER_MODEL_DEFAULT_LEVEL:
        if needle in model_id:
            return level
    return _GEMINI_DEFAULT_THINKING_LEVEL


def compose_thinking_config(
    *,
    reasoning_effort: ReasoningEffort | None,
    model_id: str,
) -> gtypes.ThinkingConfig:
    """Build the ``ThinkingConfig`` for this turn.

    ``include_thoughts=True`` is sent unconditionally so any thinking-
    capable model emits reasoning deltas alongside the answer.
    ``thinking_level`` is set on every request: explicitly to the
    resolved ``reasoning_effort`` when the user opted in via the
    ``/thinking`` picker, or to the per-model safe default returned
    by :func:`default_thinking_level_for` otherwise (see the module
    docstring for the empty-response trap this prevents).
    """
    level = default_thinking_level_for(model_id)
    if reasoning_effort is not None:
        mapped = _GEMINI_THINKING_LEVEL.get(reasoning_effort)
        if mapped is not None:
            level = mapped
    return gtypes.ThinkingConfig(include_thoughts=True, thinking_level=level)
