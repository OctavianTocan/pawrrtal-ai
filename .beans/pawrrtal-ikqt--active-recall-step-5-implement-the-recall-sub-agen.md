---
# pawrrtal-ikqt
title: 'Active Recall step 5: implement the recall sub-agent driver'
status: todo
type: task
priority: high
created_at: 2026-05-19T07:16:01Z
updated_at: 2026-05-19T07:41:46Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-5boi
---

## Goal

Write the actual helper-AI runner.

## File

`backend/app/plugins/active_recall/recall_agent.py`

## Signature

```python
async def run_active_recall(
    ctx: PreTurnHookContext,
    session: AsyncSession,
) -> str | None:
    ...
```

## Steps

1. If `settings.lcm_enabled is False` → return `None` (nothing to search).
2. Build a tool list with **only** these three (from `app.core.tools.lcm_agents`):
   - `make_lcm_grep_tool`
   - `make_lcm_describe_tool`
   - `make_lcm_expand_query_tool`
3. Pick a model via `app.core.providers.resolve_llm`. Use `settings.active_recall_model` if set, otherwise the default fast/cheap one.
4. Build `AgentLoopConfig` with `AgentSafetyConfig`:

   | Field | Value |
   |---|---|
   | `max_iterations` | `settings.active_recall_max_iterations` |
   | `max_wall_clock_seconds` | `settings.active_recall_max_wall_clock_seconds` |
   | `max_consecutive_llm_errors` | `1` |
   | `max_consecutive_tool_errors` | `2` |
   | `llm_retry_backoff_seconds` | `0.0` |

5. Use this **exact** system prompt:

   > You search long-term conversation memory. Return EITHER a single short summary (<=600 chars) of context relevant to the user message OR the literal string NONE. No preamble.

6. Drive `agent_loop`, glue all assistant text deltas into one string, trim.
7. If the final text equals `"NONE"` (case-insensitive) → return `None`.
8. If longer than `active_recall_max_summary_chars` → truncate.
9. Otherwise → return the text.

## Safety rule

Wrap the **whole thing** in `try/except`. On any failure: log a warning and return `None`. Recall **must never** break the main turn.
