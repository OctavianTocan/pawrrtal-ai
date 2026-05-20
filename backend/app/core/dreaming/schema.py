"""Pydantic output schema + parser for the dreaming pass (#341).

Decouples the reflection prompt's output shape from the runner that
consumes it. The runner imports :func:`parse_dreaming_output` and
trusts the parsed values; the prompt is in the sibling
:mod:`prompt` module.

The parser is intentionally robust:

* Accepts raw JSON.
* Accepts Markdown-fenced JSON (``"```json\\n{...}\\n```"``) — some
  reasoning models won't follow the "no fences" instruction.
* Trims leading / trailing whitespace + accidental prose lines that
  precede the JSON.
* Returns an empty :class:`DreamingOutput` rather than raising when
  the model returns invalid JSON entirely — the runner records the
  failure on the ``DreamingJob.error_text`` column instead of
  crashing the cron.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


MemoryKind = Literal["feedback", "project", "user"]
FollowupPriority = Literal["high", "normal", "low"]


class ConsolidatedMemory(BaseModel):
    """One typed memory the dreaming pass wants to persist."""

    kind: MemoryKind
    text: str = Field(min_length=1)


class DreamingPattern(BaseModel):
    """One recurring theme the pass noticed across the input window."""

    text: str = Field(min_length=1)


class Followup(BaseModel):
    """One deferred TODO the user mentioned but didn't finish."""

    text: str = Field(min_length=1)
    priority: FollowupPriority = "normal"


class DreamingOutput(BaseModel):
    """Full structured output the reflection prompt returns."""

    consolidated_memories: list[ConsolidatedMemory] = Field(default_factory=list)
    patterns: list[DreamingPattern] = Field(default_factory=list)
    followups: list[Followup] = Field(default_factory=list)
    session_summary: str = ""


# Match a Markdown JSON fence ``...```json\n{...}\n```...`` and
# extract just the inner body. Non-greedy so the ``````` close
# matches the FIRST closing fence, not the last one in the buffer.
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(?P<body>.*?)\n\s*```", re.DOTALL)


def parse_dreaming_output(raw: str) -> DreamingOutput:
    """Parse the model's raw output into a :class:`DreamingOutput`.

    Robustness contract:

    * Tolerates Markdown JSON fences.
    * Tolerates leading prose like ``"Sure! Here's the JSON:"``.
    * Returns an empty :class:`DreamingOutput` on any parse / schema
      failure so the runner can record the failure without
      bringing down the cron.

    Args:
        raw: The model's complete response string.

    Returns:
        A populated :class:`DreamingOutput`, or an empty one if the
        raw output couldn't be parsed.
    """
    candidate = _extract_json_payload(raw)
    if candidate is None:
        logger.warning("DREAMING_PARSE_NO_JSON raw_preview=%r", raw[:200])
        return DreamingOutput()

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        logger.warning(
            "DREAMING_PARSE_JSON_DECODE_ERR error=%s candidate_preview=%r",
            exc,
            candidate[:200],
        )
        return DreamingOutput()

    try:
        return DreamingOutput.model_validate(payload)
    except ValidationError as exc:
        logger.warning("DREAMING_PARSE_SCHEMA_INVALID errors=%s", exc.errors())
        return DreamingOutput()


def _extract_json_payload(raw: str) -> str | None:
    """Return the candidate JSON substring, or ``None`` if none found.

    Tries (in order):

    1. The interior of the first Markdown JSON fence, if present.
    2. The substring from the first ``{`` to the matching last
       ``}``. Naive but covers "reasoning model added a one-liner
       intro before the JSON" cases.
    3. ``None`` when neither shape produced anything.
    """
    stripped = raw.strip()
    if not stripped:
        return None

    fenced = _FENCED_JSON_RE.search(stripped)
    if fenced is not None:
        return fenced.group("body").strip()

    open_idx = stripped.find("{")
    close_idx = stripped.rfind("}")
    if open_idx == -1 or close_idx <= open_idx:
        return None
    return stripped[open_idx : close_idx + 1]


__all__ = [
    "ConsolidatedMemory",
    "DreamingOutput",
    "DreamingPattern",
    "Followup",
    "parse_dreaming_output",
]
