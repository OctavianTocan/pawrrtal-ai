"""Background reflection pass that consolidates memories between sessions (#341).

Designed in the ADR at
``frontend/content/docs/handbook/decisions/2026-05-20-dreaming-background-reflection.mdx``.
The pass runs in two modes (session-end + daily cron), both feeding
the same :class:`DreamingJob` lifecycle and writing through the
shared dedupe pipeline that :mod:`app.crud.memory` exposes.

Public surface:

- :data:`DREAMING_PROMPT` — the reflection prompt template the
  reasoning model sees on every pass.
- :class:`DreamingOutput` — Pydantic schema for the structured
  output the model returns.
- :func:`parse_dreaming_output` — robust parser that accepts the
  model's raw JSON / Markdown-fenced JSON / partial outputs.
- :func:`run_dreaming_job` — drive one job from pending →
  completed/failed (used by the scheduler + cron entry points).
- :func:`schedule_session_end_dream` /
  :func:`schedule_daily_rollup_dream` — create a job and fire its
  background runner.
"""

from app.core.dreaming.prompt import DREAMING_PROMPT
from app.core.dreaming.runner import DreamFn, run_dreaming_job
from app.core.dreaming.scheduler import (
    DreamingScope,
    schedule_daily_rollup_dream,
    schedule_session_end_dream,
)
from app.core.dreaming.schema import (
    ConsolidatedMemory,
    DreamingOutput,
    DreamingPattern,
    Followup,
    parse_dreaming_output,
)

__all__ = [
    "DREAMING_PROMPT",
    "ConsolidatedMemory",
    "DreamFn",
    "DreamingOutput",
    "DreamingPattern",
    "DreamingScope",
    "Followup",
    "parse_dreaming_output",
    "run_dreaming_job",
    "schedule_daily_rollup_dream",
    "schedule_session_end_dream",
]
