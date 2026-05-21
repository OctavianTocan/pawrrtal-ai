---
# pawrrtal-ualm
title: Tune reasoning panel disclosure timing
status: completed
type: task
priority: normal
created_at: 2026-05-20T20:41:09Z
updated_at: 2026-05-20T20:41:32Z
---

Refine the reasoning panel expand/collapse timing after the first smooth-height fix. Apply animation skill guidance for small in-flow disclosure: state-toggle easing, open in the 300ms layout range, close around 75% of open.

## Summary of Changes

- Used the available `animate` and `fixing-motion-performance` guidance to treat this as a small in-flow disclosure, where a one-shot measured-height animation is acceptable.
- Tuned `--animate-reasoning-panel-open` from 320ms ease-out-quint to 300ms ease-in-out state-toggle timing.
- Tuned `--animate-reasoning-panel-close` from 240ms custom exit to 225ms with the same state-toggle curve, preserving the roughly 75% close/open ratio.
- Verified with `just check`.
