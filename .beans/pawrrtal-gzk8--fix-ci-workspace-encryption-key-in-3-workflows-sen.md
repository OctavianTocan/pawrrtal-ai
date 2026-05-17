---
# pawrrtal-gzk8
title: 'Fix CI: WORKSPACE_ENCRYPTION_KEY in 3 workflows + sentrux layer + ChatComposerControls 500-line gate'
status: completed
type: bug
priority: high
created_at: 2026-05-09T15:42:09Z
updated_at: 2026-05-09T15:54:08Z
---

Three CI failures from PR #143 follow-on:
1. New workspace_encryption_key field in config.py is required with no default — Backend pytest, Integration suite, and Stagehand suite all fail at import-time. Add WORKSPACE_ENCRYPTION_KEY env to tests.yml, integration-tests.yml, stagehand-e2e.yml.
2. Sentrux flags be-core importing from be-models (workspace.py imports from app.models). Split: filesystem helpers stay in core/workspace.py; DB functions (get_default_workspace, list_workspaces, create_workspace, ensure_default_workspace) move to crud/workspace.py and update callers.
3. ChatComposerControls.tsx is 503 lines, fails the 500-line gate. Extract WAVEFORM_BARS + WaveformTimeline subcomponent into ChatComposerWaveform.tsx.

## Todos

- [x] Add WORKSPACE_ENCRYPTION_KEY env to tests.yml backend job
- [x] Add WORKSPACE_ENCRYPTION_KEY env to integration-tests.yml
- [x] Add WORKSPACE_ENCRYPTION_KEY env to stagehand-e2e.yml backend startup
- [x] Create backend/app/crud/workspace.py with the 4 DB functions
- [x] Strip DB functions + models imports from backend/app/core/workspace.py
- [x] Update callers: api/chat.py, api/personalization.py, api/workspace.py
- [x] Update tests/test_workspace.py imports + mock patch path
- [x] Extract WaveformTimeline + WAVEFORM_BARS to ChatComposerWaveform.tsx
- [x] Trim ChatComposerControls.tsx to import the new module
- [x] Run just check + tsc + scripts/check-file-lines.mjs

## Summary of Changes

**Fix 1 — WORKSPACE_ENCRYPTION_KEY in 3 workflows:**
- `.github/workflows/tests.yml` backend env block
- `.github/workflows/integration-tests.yml` integration env block
- `.github/workflows/stagehand-e2e.yml` backend startup env block
All three reuse the same Fernet-format dummy key already used for FERNET_KEY.

**Fix 2 — sentrux be-core → be-models layer violation:**
- New `backend/app/crud/workspace.py` holds `get_default_workspace`, `list_workspaces`, `create_workspace`, `ensure_default_workspace` — be-crud imports `Workspace` from be-models (allowed direction).
- `backend/app/core/workspace.py` now only owns filesystem helpers (`workspace_path`, `seed_workspace`, file templates). Replaced the `TYPE_CHECKING` import of `UserPersonalization` with an inline `PersonalizationLike` Protocol so be-core has zero be-models references. Renamed `_workspace_path` → `workspace_path` (now public) so crud can reuse it.
- Updated callers: `app/api/chat.py`, `app/api/personalization.py`, `app/api/workspace.py`, `tests/test_workspace.py` (split imports) and the `patch("app.core.workspace.create_workspace", ...)` → `patch("app.crud.workspace.create_workspace", ...)`.
- Verified: `just sentrux` only shows the pre-existing frontend tasks/* cycle, layer violation gone. 37 workspace tests pass.

**Fix 3 — ChatComposerControls.tsx 500-line gate:**
- Extracted `WAVEFORM_BARS` + `WaveformTimeline` into `frontend/features/chat/components/ChatComposerWaveform.tsx`.
- ChatComposerControls.tsx is now 444 lines (was 503), under the 500 ceiling.
- Verified: `bun run check` (biome + tsc + file-lines + nesting) all green.
