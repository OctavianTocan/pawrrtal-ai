---
# pawrrtal-7uy8
title: Remove reasoning panel close-end pop
status: completed
type: bug
priority: normal
created_at: 2026-05-20T20:53:46Z
updated_at: 2026-05-20T20:54:14Z
---

Closing the reasoning panel pops near the end because padding lives on the animated CollapsibleContent, leaving residual layout height until Radix removes the node. Move spacing into an inner wrapper so the animated box can collapse to true zero.

## Summary of Changes

- Root cause: `pt-2` lived on the animated `CollapsibleContent`, so close ended at `height: 0` while still retaining padding; when Radix removed the closed node, that leftover padding disappeared instantly and made following content pop upward.
- Moved the visual gap into an inner wrapper so Radix measures it as content, while the animated outer element can collapse to true zero.
- Verified with `just check`.
