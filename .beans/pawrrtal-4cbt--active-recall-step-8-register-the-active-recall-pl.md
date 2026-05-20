---
# pawrrtal-4cbt
title: 'Active Recall step 8: register the Active Recall plugin manifest'
status: todo
type: task
priority: high
created_at: 2026-05-19T07:16:02Z
updated_at: 2026-05-19T07:41:59Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-8ijt
---

## Goal

Register the plugin manifest so the registry knows Active Recall exists.

## File

`backend/app/plugins/active_recall/plugin.py`

## Code

```python
from app.core.config import settings
from app.core.plugins import Plugin, register_plugin
from app.plugins.active_recall.recall_agent import run_active_recall

active_recall_plugin = Plugin(
    id="active_recall",
    name="Active Recall",
    description=(
        "Auto-searches long-term memory before each turn so the agent "
        "remembers without being asked."
    ),
    env_keys=(),
    tool_factories=(),
    pre_turn_hooks=(run_active_recall,),
    is_activated=lambda ctx: (
        settings.active_recall_enabled and settings.lcm_enabled
    ),
)

register_plugin(active_recall_plugin)
```

## Confirm

Package is imported at startup (step 4 wired this).
