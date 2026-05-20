---
# pawrrtal-ym8n
title: 'Active Recall step 3: registry helper all_pre_turn_hooks()'
status: completed
type: task
priority: high
created_at: 2026-05-19T07:16:01Z
updated_at: 2026-05-20T10:56:28Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-nq9s
---

## Goal

Decide: **no new function in `registry.py`**. Consumers walk `all_plugins()` and project the field they need, mirroring how `_build_plugin_tools` already works in `agent_tools.py`.

## File

No file changes. This bean records a design decision only.

## Rationale

`registry.py` owns storage (`register_plugin`, `all_plugins`, `reset_for_tests`). A walk + filter + project helper (`all_pre_turn_hooks`) is a consumption concern. The existing tool-collection code in `agent_tools.py:292` already walks `all_plugins()` with activation checks inline — no registry helper. Adding one for hooks but not tools would be inconsistent. Keep the registry slim.

## What consumers do instead

Any caller that needs pre-turn hooks:

```python
from app.core.plugins import all_plugins, is_activated_by_env_keys

def collect_pre_turn_hooks(ctx: ToolContext) -> list[PreTurnHook]:
    hooks: list[PreTurnHook] = []
    for plugin in all_plugins():
        predicate = plugin.is_activated or is_activated_by_env_keys(plugin)
        if predicate(ctx):
            hooks.extend(plugin.pre_turn_hooks)
    return hooks
```

Step 9 wires this pattern into the chat router.
