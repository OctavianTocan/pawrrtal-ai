---
# pawrrtal-uecv
title: Three-level model picker (provider -> vendor -> models)
status: completed
type: feature
priority: normal
created_at: 2026-05-19T07:03:14Z
updated_at: 2026-05-19T08:04:35Z
parent: pawrrtal-7k7w
---

Switch web composer model selector and Telegram /model picker from 2-level (vendor -> models) to 3-level (provider/host -> vendor -> models). Single-vendor hosts collapse the vendor step. Also fixes title-casing bugs (Openai/Xai/Zai). Plan: docs/superpowers/plans/2026-05-19-three-level-model-picker.md

## Task Tracker

- [x] Task 1: Backend label module
- [x] Task 2: Frontend label module
- [x] Task 3: Telegram callback model
- [x] Task 4: Telegram keyboard builders
- [x] Task 5: Telegram runtime wiring
- [x] Task 6: Frontend three-level submenu
- [x] Task 7: End-to-end smoke

## Summary of Changes

Shipped the three-level model picker on both surfaces:

- **Backend label module** (`backend/app/core/providers/labels.py`) — single source of truth for `Host` / `Vendor` display strings. 6 tests assert every enum member has a label.
- **Frontend label module** (`frontend/features/chat/components/model-picker-labels.ts`) — mirrors the backend; falls back to the raw slug on unknown entries.
- **Telegram picker** (`backend/app/integrations/telegram/model_picker.py` + `model_picker_runtime.py`) — three-level walk: host → vendor → models. Single-vendor hosts collapse the vendor screen. Callback scheme grew `mdl:v:<host>` and the list shape became `mdl:l:<host>:<vendor>:<page>`. Old public names (`build_provider_keyboard`, `format_provider_picker_text`, `has_provider`) deleted.
- **Web composer** (`frontend/features/chat/components/ModelSelectorPopover.tsx` + sibling `model-selector-host-rows.tsx`) — three-level submenu with the same single-vendor collapse semantics. New fixture covers both branches.
- **Title-casing bug** ("Openai" / "Xai" / "Zai") fixed via the label maps.

Follow-ups:
- `pawrrtal-22sx` — flatten `TelegramChannel.deliver()` nesting (deferred from Task 5 because the helper extraction would have pushed `telegram.py` over the 500-line budget).
