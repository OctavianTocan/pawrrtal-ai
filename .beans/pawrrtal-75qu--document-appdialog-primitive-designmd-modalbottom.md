---
# pawrrtal-75qu
title: Document AppDialog primitive + DESIGN.md modal/bottom-sheet
status: completed
type: task
priority: normal
created_at: 2026-05-10T11:11:12Z
updated_at: 2026-05-10T11:12:54Z
---

Add AppDialog wrapper, expand DESIGN.md for modal→sheet pattern, update overlay rule, migrate feature imports from ResponsiveModal.



## Summary of Changes

- Added `frontend/components/ui/app-dialog.tsx` (`AppDialog`) as the Pawrrtal application shell over `ResponsiveModal`.
- Expanded DESIGN.md (Modal / sheet overlays): modal→bottom-sheet behavior, header/footer/body pattern, variants guidance.
- Updated `.claude/rules/react/use-octavian-overlay-for-modals.md`, `.claude/CLAUDE.md`, and how-we-work rules to prefer `AppDialog`.
- Migrated feature dialogs from `ResponsiveModal` to `AppDialog`.
