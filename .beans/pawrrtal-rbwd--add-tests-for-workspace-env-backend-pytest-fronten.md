---
# pawrrtal-rbwd
title: 'Add tests for workspace_env: backend pytest + frontend vitest'
status: completed
type: bug
priority: high
created_at: 2026-05-09T06:52:41Z
updated_at: 2026-05-09T07:09:15Z
parent: pawrrtal-c6tc
---

Project Rule 7 requires tests in the same commit as new features. Currently absent for keys.py, workspace_env.py, and WorkspacesSection.tsx. Todos: backend/tests/test_keys.py covering round-trip save/load, resolve_api_key precedence workspace then settings then None, cache invalidation on save, InvalidToken recovery, newline rejection, settings.workspace_base_dir respected; backend/tests/test_workspace_env_api.py covering GET returns all OVERRIDABLE_KEYS with empty defaults, PUT rejects unknown keys 400, PUT rejects oversized values 422, PUT rejects too many keys 422, PUT merge semantics preserves existing keys, DELETE removes one key, auth required 401 without cookie, use tmp_path and monkeypatch settings.workspace_base_dir; frontend WorkspacesSectionView vitest covering render with empty and populated state, fire onSave onDiscard onToggleToken, verify error display; optional Playwright e2e: log in -- settings -- workspaces -- set GEMINI_API_KEY -- save -- reload -- key persists.



## Summary of Changes

- backend/tests/test_keys.py — 11 unit tests covering save/load round-trip, empty-string strip, resolve_api_key precedence/fallback/None, unknown-key safety, InvalidToken quarantine, newline regex (LF/CR), and the settings.workspace_base_dir regression for the original PR's hardcoded /workspace path.
- backend/tests/test_workspace_env_api.py — 9 HTTP-level tests covering GET (empty default + post-PUT roundtrip), PUT (allowlist 400 / oversize 422 / newline injection 422 / MAX_KEYS 422 / merge semantics / empty-string strip), and DELETE (success 204 + unknown 404).
- frontend/features/settings/workspaces/WorkspacesSectionView.test.tsx — 9 vitest cases covering: render every key + Get-key link, Save/Discard disabled when clean, click-fires-onSave, Saving… label, error region as alert, onValueChange forwards typed key + value, eye toggle aria-label + onToggleVisibility, password vs text input mode.

Verified: 20 new backend tests + 9 new frontend tests all pass. Existing pytest suites (test_chat_api, test_exa_search_agent, test_gemini_stream_fn) still pass — 21 backend tests green. Existing vitest suite still green — 320 frontend tests pass.
