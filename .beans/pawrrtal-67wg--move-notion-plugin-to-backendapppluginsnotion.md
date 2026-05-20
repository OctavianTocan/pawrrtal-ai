---
# pawrrtal-67wg
title: Move Notion plugin to backend/app/plugins/notion/
status: todo
type: task
priority: high
created_at: 2026-05-19T07:41:20Z
updated_at: 2026-05-19T07:41:20Z
---

## Goal

Move the Notion plugin from `backend/app/integrations/notion/` → `backend/app/plugins/notion/` so all in-tree plugins live under one roof (`backend/app/plugins/`).

## Why

- Active Recall is landing at `backend/app/plugins/active_recall/` (epic `pawrrtal-1cfl`).
- `backend/app/integrations/` should be reserved for messaging-channel adapters (telegram, voice, webhooks). Plugins-style integrations don't belong there anymore.
- One folder = one mental model: "everything in `backend/app/plugins/` registers itself via `register_plugin`".

## Steps

### 1. Move the package

```bash
git mv backend/app/integrations/notion backend/app/plugins/notion
```

Resulting layout:

```
backend/app/plugins/
├── __init__.py            # imports each plugin subpackage to trigger registration
├── notion/
│   ├── __init__.py
│   ├── audit.py
│   ├── ntn_client.py
│   ├── plugin.py
│   └── tools/...
└── active_recall/...      # (from epic pawrrtal-1cfl)
```

### 2. Rewrite imports

Search-and-replace everywhere:

```
app.integrations.notion   →   app.plugins.notion
```

Known call sites (from `grep` at time of writing):

- `backend/app/integrations/__init__.py` (remove the notion import; see step 3)
- `backend/app/plugins/notion/__init__.py`
- `backend/app/plugins/notion/plugin.py`
- `backend/app/plugins/notion/audit.py`
- `backend/app/plugins/notion/tools/__init__.py`
- `backend/app/plugins/notion/tools/sync.py`
- `backend/app/plugins/notion/tools/read.py`
- (re-grep to be safe: `rg "app\.integrations\.notion" backend/`)

### 3. Wire registration via `backend/app/plugins/__init__.py`

Replace the side-effect import that currently lives in `backend/app/integrations/__init__.py`:

```python
# backend/app/plugins/__init__.py
"""In-tree plugin packages. Importing this module triggers each
subpackage's import, which registers the plugin against
``app.core.plugins.registry``.
"""
from app.plugins import notion          # noqa: F401
from app.plugins import active_recall   # noqa: F401  (added in epic pawrrtal-1cfl)
```

Then in `backend/app/integrations/__init__.py`:

- Remove `from app.integrations import notion`.
- Add `from app import plugins  # noqa: F401` **or** update wherever `import app.integrations` is currently used to do `import app.plugins` instead.
- Update the module docstring — `integrations/` is now just channel adapters.

Verify: whatever currently triggers `import app.integrations` at startup still ends up importing `app.plugins` (so registration fires).

### 4. Update non-code references

These are doc/comment strings, not imports — fix them too:

- `backend/Dockerfile` (line ~44 comment about `app/integrations/notion/ntn_client.py`)
- `backend/.env.example` (line ~348: `Notion plugin (backend/app/integrations/notion/) …`)
- `backend/app/core/keys.py` (line ~64 comment)
- Any handbook/ADR pages referencing the old path (`rg "integrations/notion" .`)

### 5. Local gate

```bash
# imports clean?
cd backend && uv run python -c "import app.plugins; import app.integrations"

# lint + format
just check

# backend tests
cd backend && uv run pytest -q
```

### 6. Commit

One logical commit. Body should mention this is a pure move + import rewrite (no behavior change), and link the Active Recall epic `pawrrtal-1cfl` as the reason.

## Out of scope

- No changes to the Notion plugin's behavior, tools, or audit logic.
- No registry/Plugin dataclass changes (that's the Active Recall epic).
