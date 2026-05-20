---
# pawrrtal-fbpz
title: 'Active Recall step 11: ADR + docs handbook entry'
status: todo
type: task
priority: normal
created_at: 2026-05-19T07:16:02Z
updated_at: 2026-05-19T07:42:07Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-rpxw
---

## Goal

Write an ADR (architecture decision record) so future-you knows why this exists.

## File

`frontend/content/docs/handbook/decisions/2026-05-19-active-recall-pre-turn-hook.md`

## Cover

- **Motivation** — agents often forget to call LCM tools on their own.
- **Design** — a tiny helper sub-agent runs before each turn, reusing `agent_loop`. Its short note gets pasted into the main system prompt.
- **Safety budget** — 3 iterations, 15 seconds, fast cheap model. Never raises.
- **Opt-in** — behind `active_recall_enabled` flag.
- **Why a plugin** — we added `pre_turn_hooks` to the `Plugin` dataclass so any future plugin can do the same trick.
- **Location** — `backend/app/plugins/active_recall/`.
- **Link** — epic bean `pawrrtal-1cfl`.

## After

```bash
bun run design:lint
```

(No-op for the handbook but cheap to verify nothing else broke.)
