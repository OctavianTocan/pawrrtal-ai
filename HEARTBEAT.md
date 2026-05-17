---
# Tracer-bullet heartbeat config — single check.
#
# The runtime reads this file from the path in HEARTBEAT_MD_PATH
# (defaults to <repo>/HEARTBEAT.md when running locally). Each item
# under `checks` is parsed into a `HeartbeatCheck` and is reachable via
# `POST /api/v1/heartbeat/run` (see backend/app/api/heartbeat.py).
checks:
  - name: pulse
    # Interval the future JobScheduler-driven registrar will use. Not
    # consumed by the manual endpoint that ships in this slice, but
    # validated at parse time so misconfigs surface early.
    interval_seconds: 1800
    prompt: |
      Heartbeat: confirm I'm still alive. Report the wall-clock time and
      that the conversation pipeline is reachable.
---

# Heartbeat

Pawrrtal's heartbeat is a periodic background turn that re-enters a
conversation on a schedule and surfaces anything noteworthy. It mirrors
[openclaw's heartbeat](https://docs.openclaw.ai/gateway/heartbeat): the
YAML front matter above defines the checks, and the body is free-form
context the future LLM-backed runner will read alongside the prompt.

## Current scope (this slice)

Manual-trigger vertical slice that proves the runner end-to-end:

1. `POST /api/v1/heartbeat/run` loads this file, picks the named (or
   first) check, and writes a heartbeat-tagged assistant message into
   the requested conversation.
2. The existing chat UI surfaces the message via the same
   `GET /api/v1/conversations/{id}/messages` path it already polls, so
   no frontend change is needed to see the result.

## Out of scope (follow-up)

- **Scheduled invocation.** `TODO(heartbeat-scheduler)` —
  pawrrtal already ships a higher-level `JobScheduler` (see
  `backend/app/core/scheduler.py`) that runs cron-style work and
  integrates with the EventBus. The follow-up registers
  `run_heartbeat` there rather than booting a parallel APScheduler.
- **Real LLM-backed run.** `TODO(heartbeat-llm)` — feed `check.prompt`
  through the agent loop with the configured tools and persist the
  streamed timeline. The current runner just echoes the check name +
  prompt into the assistant message so the wiring is observable.
