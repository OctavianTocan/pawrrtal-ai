---
# pawrrtal-0k7p
title: 'chore(frontend): migrate /users/me callers to canonical /api/v1/users/me'
status: todo
type: task
priority: low
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-27T20:08:18Z
---

Backend now exposes /api/v1/users/me as the canonical path (added during paw v1, commit a8ac063c) and keeps /users/me as a compat alias. Migrate the frontend hooks (useAuth, useCurrentUser, etc.) off the alias so the alias can eventually be removed. Parent: pawrrtal-6cnv.
