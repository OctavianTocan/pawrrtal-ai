---
# pawrrtal-fmo5
title: 'Fix page feedback: / landing page and onboarding'
status: in-progress
type: task
priority: high
created_at: 2026-05-09T13:29:22Z
updated_at: 2026-05-09T13:29:22Z
---

Address 10 UI feedback items from design review:

1. Submit button size matches mic/model-selector at size-8 but visually heavier — adjust
2. Onboarding StepMessaging needs loading state for Telegram connection check
3. New Session button needs visibility when navbar is collapsed  
4. Default permissions color hard to see in light mode
5. Keyboard Shortcuts dropdown item should open a modal
6. Voice meter waveform: bars should start right-aligned and respond to meterLevel
7. StepIdentity goal chips not using correct foreground design tokens
8. Three multi-select buttons missing cursor-pointer
9. Selected model indicator uses tick — change approach
10. Plan button needs yellow color; send button should match when in plan mode

Also add DESIGN.md note about loader/skeleton pattern for UI that fetches data on mount.
