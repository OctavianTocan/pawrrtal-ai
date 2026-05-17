---
# pawrrtal-c2cj
title: Shared tool display metadata
status: completed
type: feature
priority: normal
created_at: 2026-05-17T10:54:03Z
updated_at: 2026-05-17T11:09:19Z
---

Add shared tool-level display metadata for web and Telegram tool-call rendering.

- [x] Add backend display contract and tool formatters
- [x] Propagate display metadata through Gemini and Claude tool_use events
- [x] Persist and render display metadata in web chat
- [x] Update Telegram rendering to use friendly display text
- [x] Add/update backend and frontend tests
- [x] Commit, push, and open PR to development


## Summary of Changes

- Added shared optional tool display metadata on AgentTool and tool_use stream events.
- Propagated display payloads through Gemini, Claude, chat persistence, SSE, frontend reducer state, and Telegram delivery.
- Added safe display helpers for path/query/title truncation and sensitive argument hiding.
- Added first-pass display formatters for workspace, search, artifact, image, markdown conversion, send-message, Telegram capability, and LCM tools.

## Verification

- Backend focused tests: 99 passed.
- Frontend focused chat tests: 15 passed.
- just check passed.
- bun run check passed.
- git diff --check passed.
- File line and nesting checks passed for touched surfaces.
