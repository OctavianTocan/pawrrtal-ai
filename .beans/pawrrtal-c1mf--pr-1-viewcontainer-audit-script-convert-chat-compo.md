---
# pawrrtal-c1mf
title: 'PR 1: View/Container audit script + convert chat composer in-place'
status: completed
type: task
priority: high
created_at: 2026-05-10T21:45:40Z
updated_at: 2026-05-10T22:04:55Z
parent: pawrrtal-f1vm
---

First PR in the react-chat-composer extraction. Lands the View/Container audit script in advisory mode and converts the four chat composer files to the View/Container pattern in their current location. No package work yet — strictly in-place refactor + tooling. See docs/plans/extract-react-chat-composer.md §10 for details.

## Todo

- [x] Create branch feat/extract-react-chat-composer from feat/react-overlay-submodule-create-project
- [x] Write scripts/check-view-container.mjs (TS compiler API; IMPURE_VIEW + MONOLITH checks; advisory default, STRICT_VC=1 strict)
- [x] Run script once to harvest pre-existing offenders, seed EXEMPT_FILES inline with TODO tags
- [x] Wire bun run check:view-container into package.json scripts and the bun run check fan-out
- [x] Split ChatComposer.tsx → container + ChatComposerView.tsx
- [x] Split ChatComposerControls.tsx into per-control files (AttachButton, PlanButton, AutoReviewSelector + view, VoiceMeter, WaveformTimeline, ComposerTooltip) and helpers
- [x] Split ModelSelectorPopover.tsx → container + ModelSelectorPopoverView.tsx
- [x] Clean pass on ChatPromptSuggestions.tsx (already mostly pure)
- [x] Thorough TSDoc on every export across the touched files
- [x] Update biome + tsc + existing tests — zero new warnings
- [x] Audit script reports zero new offenders for the four chat composer files
- [x] Open PR with conventional title 'chore: add view/container audit + convert chat composer to View/Container in-place' — #166

## Summary of Changes

Opened https://github.com/OctavianTocan/Pawrrtal-AI/pull/166 covering:

- New scripts/check-view-container.mjs (TS compiler API; IMPURE_VIEW + MONOLITH checks; advisory default; STRICT_VC=1 strict). Wired into bun run check.
- Four chat composer files converted to View/Container in-place:
  - ChatComposer.tsx → ChatComposer.tsx + ChatComposerView.tsx
  - ChatComposerControls.tsx → host shell + AutoReviewSelector.tsx + AutoReviewSelectorView.tsx + safety-mode-meta.tsx
  - ModelSelectorPopover.tsx → ModelSelectorPopover.tsx + ModelSelectorPopoverView.tsx + model-selector-data.ts + ProviderLogo.tsx + ModelRow.tsx + ReasoningRow.tsx
  - ChatPromptSuggestions.tsx was already pure — no split needed
- Plan + ADR + beans tracking landed in the same branch.

All checks pass: biome + tsc + file-lines + nesting + view-container all OK.
