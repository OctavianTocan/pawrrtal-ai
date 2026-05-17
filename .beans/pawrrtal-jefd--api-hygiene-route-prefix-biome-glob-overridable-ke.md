---
# pawrrtal-jefd
title: 'API hygiene: route prefix, biome glob, OVERRIDABLE_KEYS dedup'
status: completed
type: task
priority: normal
created_at: 2026-05-09T06:52:44Z
updated_at: 2026-05-09T07:12:35Z
parent: pawrrtal-c6tc
---

Smaller hygiene cleanups. Todos: decide route prefix -- rename /api/v1/workspace to /api/v1/workspaces/me/env or /api/v1/workspaces/env for consistency with existing /api/v1/workspaces, update frontend API_ENDPOINTS.workspace.env; biome.json:29 verify whether the \!frontend/lib change still excludes the react-dropdown submodule but lints frontend/lib/api.ts -- if broken switch to \!frontend/lib/react-dropdown or its glob form; OVERRIDABLE_KEYS dedup: add cross-reference comments in keys.py and WorkspacesSection.tsx pointing at each other; optional split inline route handlers in workspace_env.py into module-level functions for testability.



## Summary of Changes

- biome.json:29 — narrowed `\!frontend/lib` to `\!frontend/lib/react-dropdown`. The previous form excluded the entire frontend/lib/ tree from formatting + linting (api.ts, channels.ts, etc.), which silently dropped coverage for non-submodule lib code.
- backend/app/core/keys.py — fixed cross-reference comment to point at the new frontend location (frontend/features/settings/workspaces/use-workspace-env.ts:WORKSPACE_ENV_KEY_IDS).
- frontend/features/settings/workspaces/use-workspace-env.ts — already has a cross-reference back to backend/app/core/keys.py from Bean E.

Route prefix decision: KEEP /api/v1/workspace/env (singular). The endpoint represents the user's per-account workspace config, not a member of a /workspaces collection. Renaming would break the freshly-introduced API surface for cosmetic gain. The plurality concern was cosmetic — the architectural distinction (per-user vs per-workspace) is more important than alignment with /api/v1/workspaces.

Verified: just check clean (only pre-existing warnings); 41 backend tests + 35 frontend settings tests pass.
