---
# pawrrtal-ow5d
title: Backend label module (TDD) — Host/Vendor display-label labels.py
status: completed
type: task
priority: normal
created_at: 2026-05-19T07:04:31Z
updated_at: 2026-05-19T07:05:46Z
---

Create backend/app/core/providers/labels.py and backend/tests/test_provider_labels.py following TDD. Single source of truth for Host/Vendor display strings.

## Summary of Changes

- Created  with , , , , , .
- Created  with 6 tests (TDD: red → green).
- Edge case:  /  catch  from  and reraise as  for consistent dict-lookup semantics.
- All 6 tests pass;  +  clean.
- Commit: 4c343544
