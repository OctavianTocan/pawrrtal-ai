---
# pawrrtal-rpxw
title: 'Active Recall step 10: tests using ScriptedStreamFn'
status: todo
type: task
priority: high
created_at: 2026-05-19T07:16:02Z
updated_at: 2026-05-19T07:42:05Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-pney
---

## Goal

Tests using `ScriptedStreamFn` from `tests.agent_harness` (a fake LLM you give a script to).

## New files

```
backend/tests/plugins/active_recall/
├── test_recall_agent.py
└── test_plugin_wiring.py
```

## Cases for `run_active_recall`

| # | Helper script | Expected result |
|---|---|---|
| a | calls `lcm_grep`, then emits `"short summary"` | returns `"short summary"` |
| b | emits `"NONE"` | returns `None` |
| c | hits `max_iterations` | returns `None`; assert `script.call_count == 3` |
| d | provider raises | returns `None`, no exception leaks out |

## Turn-runner integration test

- With `active_recall_enabled=False` → the hook is **never** called.
- With it enabled and a stub hook returning `"recalled X"` → the `system_prompt` the main provider receives contains:
  ```
  <recalled_context>recalled X</recalled_context>
  ```
