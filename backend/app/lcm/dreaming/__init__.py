"""Background reflection pass that consolidates memories between sessions (#341).

Designed in the ADR at
``frontend/content/docs/handbook/decisions/2026-05-20-dreaming-background-reflection.mdx``.
The pass runs in two modes (session-end + daily cron), both feeding
the same :class:`DreamingJob` lifecycle and writing through the
shared dedupe pipeline that :mod:`app.lcm.memory_crud` exposes.

Public surface:

- :data:`DREAMING_PROMPT` — the reflection prompt template the
  reasoning model sees on every pass.
- :class:`DreamingOutput` — Pydantic schema for the structured
  output the model returns.
- :func:`parse_dreaming_output` — robust parser that accepts the
  model's raw JSON / Markdown-fenced JSON / partial outputs.

The actual job runner + scheduler integration lives in
:mod:`app.lcm.dreaming.runner` (added in a stacked follow-up); this
module owns the pure types + prompt so they're unit-testable without
the LCM background scheduler in scope.
"""

from app.lcm.dreaming.prompt import DREAMING_PROMPT
from app.lcm.dreaming.schema import (
    ConsolidatedMemory,
    DreamingOutput,
    DreamingPattern,
    Followup,
    parse_dreaming_output,
)

__all__ = [
    "DREAMING_PROMPT",
    "ConsolidatedMemory",
    "DreamingOutput",
    "DreamingPattern",
    "Followup",
    "parse_dreaming_output",
]
