---
# pawrrtal-0bss
title: Flatten 14 nesting-depth offenders deferred from PR469 unblock
status: todo
type: task
priority: normal
created_at: 2026-05-28T14:31:46Z
updated_at: 2026-05-28T14:31:46Z
---

These 14 functions exceed the nesting-depth budget (3) and were added to EXEMPT_FUNCTIONS in scripts/check-nesting.py during the PR469 CI unblock. Flatten each via guard clauses / extracted helpers and remove its EXEMPT entry. List captured in the script's comments.
