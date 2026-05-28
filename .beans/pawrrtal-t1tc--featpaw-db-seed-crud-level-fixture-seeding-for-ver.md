---
# pawrrtal-t1tc
title: 'feat(paw): db seed — CRUD-level fixture seeding for verify scenarios'
status: todo
type: feature
priority: high
created_at: 2026-05-28T09:14:50Z
updated_at: 2026-05-28T09:14:50Z
---

From paw v3 brainstorm Thread 3. Add 'paw db seed conversations/memories/...' that calls the same crud/ helpers the API uses. Lets verify scenarios prepare DB shape without driving the full HTTP path (50 chat turns to set up '50-conversations sidebar' test is absurd). Unblocks pawrrtal-7uo7 (verify lcm-active-recall) without needing pawrrtal-x9u4 (the missing HTTP surface). Constraint: never raw SQL — typed helpers only.
