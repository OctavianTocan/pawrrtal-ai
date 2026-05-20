---
# pawrrtal-8ijt
title: 'Active Recall step 6: wire pre-turn hooks into turn_runner.run_turn'
status: todo
type: task
priority: high
created_at: 2026-05-19T07:16:01Z
updated_at: 2026-05-19T07:41:47Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-jkxd
---

## Goal

Make the main turn actually call the pre-turn hooks.

## File

`backend/app/channels/turn_runner.py`

## 1. Extend `ChatTurnInput`

Add two new optional fields:

```python
pre_turn_hooks: list[PreTurnHook] | None = None
workspace_id: UUID | None = None
```

## 2. Run hooks inside `run_turn`

Good spot: just before or right after `_load_history_and_persist`, **before** opening `llm_span`.

- If `pre_turn_hooks` is set, loop over them **one at a time** (serial, not parallel).
- For each hook:
  - Build a `PreTurnHookContext`.
  - Wrap the call in its own short `asyncio.timeout`.
  - `await` it.
- Collect non-`None` results into a list.

## 3. Glue results

Join them into one `RECALLED CONTEXT` string.

## 4. Pass it through

Hand it to `system_prompt_for_turn` via a new optional `extra_context` kwarg (step 7 adds that kwarg).

## 5. Log one structured line per hook

```
ACTIVE_RECALL conversation_id=... ms=... status=text|none|error chars=...
```
