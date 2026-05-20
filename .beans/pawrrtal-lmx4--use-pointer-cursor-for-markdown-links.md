---
# pawrrtal-lmx4
title: Use pointer cursor for markdown links
status: completed
type: task
priority: normal
created_at: 2026-05-20T20:33:48Z
updated_at: 2026-05-20T20:34:40Z
---

Page feedback for chat message markdown: links rendered inside Streamdown should show the pointer cursor on hover.

## Summary of Changes

- Added a Streamdown wrapper cursor rule in `frontend/components/ai-elements/message.tsx` so markdown-rendered link buttons show the pointer cursor.
- Verified with `just check`.
