---
# pawrrtal-0k7p
title: 'chore(frontend): migrate /users/me callers to canonical /api/v1/users/me'
status: completed
type: task
priority: low
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-27T23:58:51Z
---

Backend now exposes /api/v1/users/me as the canonical path (added during paw v1, commit a8ac063c) and keeps /users/me as a compat alias. Migrate the frontend hooks (useAuth, useCurrentUser, etc.) off the alias so the alias can eventually be removed. Parent: pawrrtal-6cnv.

## Summary of Changes

Only one source-of-truth literal existed in the frontend: `frontend/lib/api.ts`. The `auth.me` and `users.get` endpoint constants were repointed to the canonical `/api/v1/users/*` paths; every caller (`useCurrentUser`, etc.) flows through `API_ENDPOINTS.auth.me` so no other touches were needed at call sites.

Files modified (4):

- `frontend/lib/api.ts` — `auth.me`: `/users/me` -> `/api/v1/users/me`; `users.get`: `/users` -> `/api/v1/users` (plus JSDoc).
- `frontend/hooks/use-current-user.ts` — JSDoc references updated to `/api/v1/users/me`.
- `frontend/features/settings/sections/GeneralSection.tsx` — JSDoc reference updated.
- `frontend/features/app-shell/AppShell.tsx` — JSDoc reference updated.

No test mocks referenced `/users/me` (verified `rg -n '['\"]/users' frontend/test frontend/e2e`). No Next.js internal route at `frontend/app/api/users/*` exists. The dev-login proxy was not touched (it targets `/auth/dev-login`, not the users router).
