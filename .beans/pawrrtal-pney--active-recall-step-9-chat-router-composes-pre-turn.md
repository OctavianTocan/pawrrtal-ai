---
# pawrrtal-pney
title: 'Active Recall step 9: chat router composes pre_turn_hooks for the turn'
status: todo
type: task
priority: high
created_at: 2026-05-19T07:16:02Z
updated_at: 2026-05-20T10:56:18Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-4cbt
---

## Goal

HTTP chat endpoint collects activated hooks by walking `all_plugins()` directly (no registry helper), then passes them into the turn.

## File

`backend/app/api/chat.py` — where `ChatTurnInput` is constructed.

## Steps

1. Import what you need:
   ```python
   from app.core.plugins import all_plugins, is_activated_by_env_keys, ToolContext
   ```
2. Build an activation context:
   ```python
   ctx = ToolContext(
       workspace_id=workspace_id,
       workspace_root=workspace_root,
       user_id=user_id,
       send_fn=None,
   )
   ```
3. Walk plugins and collect hooks — mirrors how `_build_plugin_tools` in `agent_tools.py` already works:
   ```python
   pre_turn_hooks: list[PreTurnHook] = []
   for plugin in all_plugins():
       predicate = plugin.is_activated or is_activated_by_env_keys(plugin)
       if predicate(ctx):
           pre_turn_hooks.extend(plugin.pre_turn_hooks)
   ```
4. Pass them in:
   ```python
   ChatTurnInput(
       ...,
       pre_turn_hooks=pre_turn_hooks or None,
       workspace_id=workspace_id,
   )
   ```

## Telegram (`backend/app/channels/telegram.py`)

- Wire recall in **only if** you want it on Telegram too.
- For **v1** it's fine to skip Telegram — just call out that choice in the PR description.

## Why not a registry helper

See step 3 — the registry stays slim. Consumers project the fields they need, just like `_build_plugin_tools` does for tool factories.
