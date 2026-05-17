---
# pawrrtal-17do
title: 'Telegram bot delivery + memory regressions: file 4 GitHub issues'
status: completed
type: task
priority: high
created_at: 2026-05-17T20:59:04Z
updated_at: 2026-05-17T21:00:51Z
---

Diagnose and file GitHub issues for: (1) thinking text shows literal '**' chars instead of rendered markdown, (2) tool-call placeholder grows across blocks instead of new message per thinking/tools transition, (3) Paw discovers tools by list_dir instead of using its prompt, (4) memory files re-read on every turn because AGENTS.md 'Session Startup' fires per turn.


## Summary of Changes

Diagnosed root causes for all 4 Telegram bot issues and filed GitHub issues:

- **#287** — `telegram: thinking text shows literal **markers**` — `thinking_html` (`backend/app/channels/telegram_delivery.py:78-80`) only HTML-escapes and never runs through `md_to_telegram_html`.
- **#288** — `telegram: thinking/tools/thinking should produce 3 separate messages` — `_handle_tool_use` and `_handle_thinking` in `backend/app/channels/telegram.py` each maintain a single growing buffer per kind for the whole turn; no block-transition logic.
- **#289** — `paw: agent uses list_dir/read_file to discover its own tools` — system prompt has no tool inventory; AGENTS.md template frames the workspace as the source of truth for capabilities.
- **#290** — `paw: memory + identity files re-read on every turn` — AGENTS.md template's "On every session start, read…" section (`backend/app/core/workspace.py:108-115`) is concatenated into the system prompt verbatim; the model treats every turn as a fresh session.

All four are bugs, all filed against `OctavianTocan/Pawrrtal-AI` with the appropriate `area: telegram` / `area: backend` labels.
