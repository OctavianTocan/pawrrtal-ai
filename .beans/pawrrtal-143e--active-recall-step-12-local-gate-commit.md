---
# pawrrtal-143e
title: 'Active Recall step 12: local gate + commit'
status: todo
type: task
priority: normal
created_at: 2026-05-19T07:16:02Z
updated_at: 2026-05-19T07:42:09Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-fbpz
---

## Goal

Final local gate + ship.

## Run in this order

```bash
# 1. biome + ruff
just check

# 2. plugin tests
cd backend && uv run pytest tests/plugins/active_recall -q

# 3. turn-runner tests (or whatever file covers run_turn)
cd backend && uv run pytest tests/channels/test_turn_runner.py -q

# 4. frontend typecheck — should be a no-op; proves no accidental FE change
cd frontend && bun run typecheck
```

## Commit

One logical commit. In the body, reference:

- the epic bean: `pawrrtal-1cfl`
- every step bean ID (1–11)

## Push

```bash
just push
```
