---
# pawrrtal-ovuh
title: 'Rewrite WorkspacesSection: TanStack Query + View/Container + abort + UX'
status: completed
type: bug
priority: high
created_at: 2026-05-09T06:52:37Z
updated_at: 2026-05-09T07:06:43Z
parent: pawrrtal-c6tc
---

Frontend overhaul of frontend/features/settings/sections/WorkspacesSection.tsx. Todos: split into WorkspacesSection container plus WorkspacesSectionView pure presentation with no hooks except useId; replace useEffect+fetchEnv with useAuthedQuery for caching dedup and AbortController for free; replace handleSave with useMutation and invalidate workspace-env cache on success; parse error.detail from API responses instead of raw API Error 422 string; add cursor-pointer to eye-toggle button at line 158 per CLAUDE.md Rule 5; add as const to OVERRIDABLE_KEYS array and derive OverridableKeyId union; add TSDoc to WorkspaceEnvResponse and OVERRIDABLE_KEYS; add explicit return types to handleChange handleSave handleDiscard toggleShowToken; decide DELETE wiring -- per-row Clear button OR remove the DELETE route; mark loading state during initial query so inputs do not flash empty.



## Summary of Changes

- New: frontend/features/settings/workspaces/use-workspace-env.ts — TanStack Query hooks (useWorkspaceEnv, useUpsertWorkspaceEnv) bound to useAuthedFetch + useAuthedQuery, plus extractApiErrorMessage helper that parses FastAPI's detail field out of the wrapper's 'API Error: 422 Body: ...' string.
- New: frontend/features/settings/workspaces/WorkspacesSectionView.tsx — pure-presentation view with no hooks except for accessibility. Receives every value/handler as a prop. Eye toggle now has cursor-pointer and aria-label.
- Rewrote frontend/features/settings/sections/WorkspacesSection.tsx as a thin container; manages working-copy state, dirty tracking, mutation reset on discard. Uses the new query/mutation pair so AbortController, caching, and dedup come for free.
- WORKSPACE_ENV_KEY_IDS uses 'as const satisfies readonly string[]' and exports WorkspaceEnvKey union type — no more bare-string drift between key references.
- Errors from save fall back to a friendly message; 422 detail surfaces as 'Value for GEMINI_API_KEY exceeds 512 characters.' instead of 'API Error: 422 ...'.
- Fixed pre-existing lint in test_exa_search.py and test_conversation_api.py (unused imports), plus formatter delta on workspace_env.py + gemini_provider.py.
- DELETE endpoint stays on backend; UI doesn't call it (clearing a field + Save now correctly omits empty values from the encrypted file via save_workspace_env's strip step in Bean A).

Verified: bunx tsc --noEmit clean, just check clean (only pre-existing warnings remain unrelated to this work).
