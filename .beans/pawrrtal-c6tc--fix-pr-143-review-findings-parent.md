---
# pawrrtal-c6tc
title: 'Fix PR #143 review findings (parent)'
status: completed
type: epic
priority: high
created_at: 2026-05-09T06:50:53Z
updated_at: 2026-05-09T07:12:48Z
---

Parent bean tracking the fix workstream for all PR #143 review findings. Children cover keys.py, Alembic migration, WorkspacesSection, .env/config, provider consistency, tests, and API hygiene.



## Summary of Changes

All 7 child beans completed:

- pawrrtal-jmhz: keys.py overhaul — moved out of providers/, replaced /workspace hardcode with settings.workspace_base_dir, added InvalidToken quarantine, newline rejection, Fernet caching, removed unbounded module cache, stripped empty values on save, removed dead guards.
- pawrrtal-4her: Alembic 010_drop_api_keys.py — drops the api_keys table, also acts as a merge revision collapsing the two pre-existing heads into a single linear graph.
- pawrrtal-s6q6: env/config cleanup — added WORKSPACE_ENCRYPTION_KEY to .env.docker, removed Chinese mojibake from .env.example, deleted registration_secret field, cleared invite_code references in admin_seed and users.
- pawrrtal-hpfq: provider/factory consistency — GeminiLLM user_id now Optional, removed double-fallback dead code in stt/agent_tools/agents (folded into A).
- pawrrtal-ovuh: WorkspacesSection rewrite — TanStack Query hook + view/container split + AbortController + parsed error.detail + cursor-pointer + as-const literal union.
- pawrrtal-rbwd: tests — 11 unit tests for keys.py + 9 HTTP tests for workspace_env_api + 9 vitest cases for WorkspacesSectionView.
- pawrrtal-jefd: API hygiene — biome glob narrowed to react-dropdown only; cross-reference comments fixed.

Final gate: just check passes (no errors, only pre-existing warnings). 41 backend tests + 35 frontend settings tests + full vitest suite (320 tests) all green. tsc --noEmit clean.

Route prefix /api/v1/workspace/env kept singular intentionally — it's per-user config, not a /workspaces collection member. Documented in Bean G's summary.
