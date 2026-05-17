---
# Tracer-bullet heartbeat config — single check, fixed interval.
#
# The runtime reads this file from the path in HEARTBEAT_MD_PATH (defaults
# to <repo>/HEARTBEAT.md when running locally).  Each item under `checks`
# is registered as an APScheduler interval job in
# `backend/app/api/heartbeat.py::heartbeat_lifespan`.
checks:
  - name: pulse
    # Interval between runs.  Kept short for the tracer so an operator can
    # see the wiring fire without waiting.  Tune per-check once the LLM
    # call lands (see the inline TODO in `run_heartbeat`).
    interval_seconds: 1800
    prompt: |
      Heartbeat: confirm I'm still alive.  Report the wall-clock time and
      that the conversation pipeline is reachable.
---

# Heartbeat

Pawrrtal's heartbeat is a periodic background turn that re-enters a
conversation on a schedule and surfaces anything noteworthy.  It mirrors
[openclaw's heartbeat](https://docs.openclaw.ai/gateway/heartbeat): the
YAML front matter above defines the checks, and the body is free-form
context the future LLM-backed runner will read alongside the prompt.

## Current scope

Tracer-bullet vertical slice — proves the whole pipeline end-to-end with
the smallest honest implementation:

1. APScheduler boots inside the FastAPI lifespan when
   `HEARTBEAT_ENABLED=true` and a target user + conversation are
   configured.
2. Each check registered above gets an `IntervalTrigger` job.
3. The job opens an async session, reads this file, and writes a
   heartbeat-tagged assistant message into the configured conversation.
4. The existing chat UI picks the message up via the usual
   `GET /api/v1/conversations/{id}/messages` poll/refresh path.

The LLM-backed run (real agent turn, tool access, thinking-and-tooluse
timeline) is the next slice — see the TODO in
`backend/app/api/heartbeat.py::run_heartbeat`.
