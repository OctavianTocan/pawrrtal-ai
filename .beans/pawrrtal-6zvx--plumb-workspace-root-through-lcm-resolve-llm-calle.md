---
# pawrrtal-6zvx
title: Plumb workspace_root through LCM resolve_llm callers (background summarization)
status: todo
type: task
priority: normal
created_at: 2026-05-17T09:36:14Z
updated_at: 2026-05-17T09:36:14Z
blocked_by:
    - pawrrtal-x9u4
---

## Context

Follow-up to pawrrtal-x9u4 (Claude SDK workspace isolation). After that fix:

- **Security is closed**: `setting_sources=[]` in `claude_provider.py` makes every Claude SDK invocation ignore filesystem-driven settings, CLAUDE.md, hooks, and `.mcp.json` — no matter what `cwd` is.
- **`cwd` is now wired** for the chat router, telegram bot, and event-bus webhook handlers — those callers had a `workspace_root` naturally in scope.

The LCM (Latent Conversation Memory) background summarization path still calls `resolve_llm` without `workspace_root`. The chain is 5–6 functions deep:

```
turn_runner.schedule_lcm_compaction
  -> _lcm_compact_bg
    -> compact_leaf_if_needed
      -> run_condensation_cascade
        -> _condense_at_depth
          -> resolve_llm           <-- needs workspace_root
```

Plus a separate `lcm_expand_query` tool factory (`backend/app/core/tools/lcm_expand_query.py:96`) that also calls `resolve_llm` without a workspace.

## Why this is cleanup, not security

LCM only summarizes conversation history. It never enables tools, never touches the filesystem, never runs MCP servers. The only thing `cwd` controls for the LCM path is where the Claude SDK writes its (unused) transcript directory — currently the backend's working directory, which is just operationally untidy.

## Work

- [ ] Add `workspace_root: Path | None` to `schedule_lcm_compaction`, `_lcm_compact_bg`, `compact_leaf_if_needed`, `run_condensation_cascade`, `_condense_at_depth`
- [ ] Plumb it through to the `resolve_llm` calls at `backend/app/core/lcm/__init__.py:365` and `backend/app/core/lcm/condense.py:158`
- [ ] Update `lcm_expand_query` factory to accept `workspace_root` and pass it (the chat router already has `workspace_root` in scope when building agent tools)
- [ ] Update LCM tests to assert the new parameter is honored
