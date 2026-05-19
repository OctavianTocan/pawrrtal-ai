---
# pawrrtal-uecv
title: Three-level model picker (provider -> vendor -> models)
status: in-progress
type: feature
priority: normal
created_at: 2026-05-19T07:03:14Z
updated_at: 2026-05-19T07:34:46Z
parent: pawrrtal-7k7w
---

Switch web composer model selector and Telegram /model picker from 2-level (vendor -> models) to 3-level (provider/host -> vendor -> models). Single-vendor hosts collapse the vendor step. Also fixes title-casing bugs (Openai/Xai/Zai). Plan: docs/superpowers/plans/2026-05-19-three-level-model-picker.md

## Task Tracker

- [x] Task 1: Backend label module
- [x] Task 2: Frontend label module
- [x] Task 3: Telegram callback model
- [x] Task 4: Telegram keyboard builders
- [ ] Task 5: Telegram runtime wiring
- [ ] Task 6: Frontend three-level submenu
- [ ] Task 7: End-to-end smoke
