---
# pawrrtal-5boi
title: 'Active Recall step 4: scaffold backend/app/plugins/active_recall/ package'
status: todo
type: task
priority: high
created_at: 2026-05-19T07:16:01Z
updated_at: 2026-05-19T07:41:44Z
parent: pawrrtal-1cfl
blocked_by:
    - pawrrtal-ym8n
---

## Goal

Make the empty folder structure for the Active Recall plugin.

## Create these files

```
backend/app/plugins/active_recall/
├── __init__.py        # empty
├── plugin.py          # Plugin manifest (filled in step 8)
└── recall_agent.py    # Helper-AI runner (filled in step 5)
```

## Make sure it loads at startup

The existing Notion plugin is registered as an import side-effect (see `backend/app/integrations/__init__.py`). Mirror that pattern for `active_recall`. Pick whichever matches conventions:

- **(a)** Add `backend/app/plugins/__init__.py` that imports `active_recall`, **or**
- **(b)** Import `app.plugins.active_recall` from `backend/app/integrations/__init__.py`.

So that a single import triggers `register_plugin(active_recall_plugin)`.
