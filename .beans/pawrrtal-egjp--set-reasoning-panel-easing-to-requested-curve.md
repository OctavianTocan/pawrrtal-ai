---
# pawrrtal-egjp
title: Set reasoning panel easing to requested curve
status: completed
type: task
priority: normal
created_at: 2026-05-20T20:51:43Z
updated_at: 2026-05-20T20:52:23Z
---

Apply user-requested timing for reasoning panel disclosure: 0.3s with cubic-bezier(.165, .84, .44, 1).

## Summary of Changes

- Set both reasoning panel open and close animations to `300ms cubic-bezier(0.165, 0.84, 0.44, 1)` as requested.
- Kept the existing measured-height keyframes and internal `pt-2` spacing implementation.
- Verified with `just check`.
