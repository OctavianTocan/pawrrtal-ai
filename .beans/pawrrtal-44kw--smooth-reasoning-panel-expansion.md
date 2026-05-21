---
# pawrrtal-44kw
title: Smooth reasoning panel expansion
status: completed
type: task
priority: normal
created_at: 2026-05-20T20:37:38Z
updated_at: 2026-05-20T20:39:46Z
---

Page feedback for chat reasoning panel: expanding and collapsing should smoothly move following message content down/up instead of feeling jerky.

## Summary of Changes

- Added reasoning-panel open/close animation tokens in `frontend/app/globals.css` that animate measured height plus opacity.
- Updated `frontend/features/chat/components/AssistantMessage.tsx` so the panel gap is inside the animated height (`pt-2`) instead of snapping as an external margin.
- Verified with `just check`.
