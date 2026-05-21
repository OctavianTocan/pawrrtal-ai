---
# pawrrtal-exjw
title: Restore natural reasoning panel easing
status: completed
type: bug
priority: normal
created_at: 2026-05-20T20:49:31Z
updated_at: 2026-05-20T20:49:54Z
---

The timing-only tweak made the reasoning panel feel linear. Restore asymmetric disclosure easing while preserving the smooth measured-height implementation and internal padding technique.

## Summary of Changes

- Root cause: the previous timing pass changed the reasoning panel to symmetric ease-in-out (`cubic-bezier(0.65, 0, 0.35, 1)`), which made measured-height interpolation feel linear.
- Restored a decelerating open curve: `320ms cubic-bezier(0.22, 1, 0.36, 1)`.
- Restored a faster accelerating close curve: `220ms cubic-bezier(0.7, 0, 0.84, 0)`.
- Kept the smooth implementation technique from `pawrrtal-44kw`: measured height animation with the spacing inside the animated box.
- Verified with `just check`.
