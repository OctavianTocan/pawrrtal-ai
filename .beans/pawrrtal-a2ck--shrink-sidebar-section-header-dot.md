---
# pawrrtal-a2ck
title: Shrink sidebar section header dot
status: completed
type: task
priority: normal
created_at: 2026-05-20T20:30:57Z
updated_at: 2026-05-20T20:32:08Z
---

Page feedback for /c/306d3fe8-a051-4f73-b37e-f6e72a7ae4a1: make the NavChats section header dot half as large without shifting the adjacent label text.

## Summary of Changes

- Updated `frontend/features/nav-chats/components/SectionHeader.tsx` so the sidebar section marker keeps its 14px layout slot while rendering a 7px inner dot.
- Verified with scoped Vitest: `bun run test -- features/nav-chats/components/SectionHeader.test.tsx`.

Follow-up: reduce the inner section-header dot another 15% without moving adjacent text.

Follow-up complete: reduced the inner dot from 7px to 6px while preserving the 14px layout slot. Verified again with scoped Vitest.
