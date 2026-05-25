"""The reflection prompt the dreaming pass sends to the reasoning model.

Held in its own module so the prompt text — load-bearing for the
quality of the dreaming output — can be tuned without touching the
runner. Mirrors the pattern used by
:mod:`app.core.lcm.condense` (compaction prompt) and
:mod:`app.core.lcm.planner` (focused-recall prompt).

The prompt asks for four structured outputs documented in the
dreaming ADR:

* ``consolidated_memories`` — typed feedback/project/user
  statements distilled from repetition.
* ``patterns`` — recurring themes across turns.
* ``followups`` — deferred work the user mentioned but the Paw
  didn't act on.
* ``session_summary`` — one-paragraph "what I learned" line.
"""

from __future__ import annotations

DREAMING_PROMPT = (
    "You are Pawrrtal's between-sessions reflection pass.\n"
    "You read a conversation transcript (or a roll-up of the last 24h "
    "of conversations) and produce four structured outputs that "
    "Pawrrtal stores for future turns.\n"
    "\n"
    "Do NOT speak directly to the user. Your output is consumed by an "
    "internal pipeline. Return a SINGLE JSON object matching this "
    "schema exactly:\n"
    "\n"
    "{\n"
    '  "consolidated_memories": [\n'
    '    {"kind": "feedback" | "project" | "user", "text": "..."}\n'
    "  ],\n"
    '  "patterns": [\n'
    '    {"text": "..."}\n'
    "  ],\n"
    '  "followups": [\n'
    '    {"text": "...", "priority": "high" | "normal" | "low"}\n'
    "  ],\n"
    '  "session_summary": "..."\n'
    "}\n"
    "\n"
    "Guidance:\n"
    "- ``feedback`` memories capture how the user wants the Paw to "
    "behave (e.g. 'user prefers concise replies', 'user dislikes "
    "emoji in technical answers').\n"
    "- ``project`` memories capture architectural / product / scope "
    "decisions (e.g. 'cost ledger lives in Postgres, not Redis').\n"
    "- ``user`` memories capture durable personal context "
    "(e.g. 'user lives in Madrid', 'user is dyslexic — wall-of-text "
    "replies are hard for them').\n"
    "- ``patterns`` are observations that span multiple turns or "
    "multiple conversations (e.g. 'this user always edits the Paw's "
    "code before running it — bias toward fewer auto-runs').\n"
    "- ``followups`` are concrete TODO items the user mentioned but "
    "did not finish. Each becomes a bean / task.\n"
    "- ``session_summary`` is one short paragraph (<=400 chars) "
    "summarising what you learned this session — read by the next "
    "session's context-assembler.\n"
    "\n"
    "If a category has nothing worth writing, return an empty list / "
    "empty string. Never write a memory just to fill the field.\n"
    "\n"
    "Do NOT wrap the JSON in Markdown code fences. Do NOT prefix it "
    "with prose. Return JSON only."
)
"""The full reflection prompt as a single string.

Stored as a module-level constant so the runner imports it once
per process and the prompt-text diff lands in a single review-able
unit when it changes."""


__all__ = ["DREAMING_PROMPT"]
