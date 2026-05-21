---
# pawrrtal-bfv3
title: Show tool chevrons only on row hover
status: completed
type: bug
priority: normal
created_at: 2026-05-20T21:01:34Z
updated_at: 2026-05-20T21:05:30Z
---

Chain-of-thought tool chevrons currently reveal when hovering the broader reasoning area. Scope the hover group to each tool row so only the row under the pointer reveals its chevron.

## Summary of Changes

- Moved the Tailwind hover group from the outer `ToolStep` wrapper to the individual tool row.
- Changed the chevron reveal selector from `group-hover:opacity-100` to `group-hover/tool-step:opacity-100`, so only the hovered row reveals its chevron.
- Verified with `just check`.

Follow-up: added `cursor-pointer` to each hovered tool row so the row communicates interactivity directly. Verified again with `just check`.

Follow-up: added `select-none` to each tool row so dragging over tool labels does not select the text. Verified again with `just check`.
