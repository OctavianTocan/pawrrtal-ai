---
# pawrrtal-oh29
title: Add inline keyboard for /verbose toggle in Telegram
status: todo
type: feature
priority: normal
created_at: 2026-05-19T12:17:47Z
updated_at: 2026-05-19T12:18:31Z
---

Add an inline keyboard (button rows) for toggling the per-conversation verbose level on Telegram, replacing or augmenting the current text-only /verbose 0|1|2 slash command flow.


## Background

Today, changing the verbose level on Telegram requires typing `/verbose 0`, `/verbose 1`, or `/verbose 2`. The slash command dispatches through `_register_telegram_command_handlers` in `backend/app/integrations/telegram/bot.py:368-447`, calls `update_conversation_verbose_level` in `backend/app/crud/channel.py:326`, and replies with a text confirmation.

Telegram already has one working inline keyboard surface — the model picker — established at `backend/app/integrations/telegram/model_picker.py` and `model_picker_runtime.py`, with callbacks dispatched in `backend/app/integrations/telegram/bot.py:449-454` via prefix-matched callback queries (prefix `mdl:`). The verbose toggle should follow the same pattern.

## Scope

- Add a `/verbose` (no-arg) variant (and/or a `/settings` entry point) that opens an inline keyboard with three buttons: `Quiet (0)`, `Normal (1)`, `Detailed (2)`. Highlight the currently-selected level (e.g. `✓ Detailed (2)`).
- Add a second `dispatcher.callback_query(...)` registration alongside the model-picker one in `backend/app/integrations/telegram/bot.py:449-454`, prefix-matched on a new namespace (e.g. `vbs:`).
- Callback handler persists the chosen level via `update_conversation_verbose_level`, edits the message in place to confirm, and fires `callback.answer(...)`.
- Keep the existing `/verbose 0|1|2` text command working as a power-user shortcut.

## Out of scope

- Persisting verbose preference per-user instead of per-conversation (the current model is per-conversation; no change here).
- Tying the keyboard into `/settings` if no `/settings` entry exists yet — the keyboard should ship even if it's only reachable via `/verbose`.

## Todo

- [ ] Add `backend/app/integrations/telegram/verbose_picker.py` (keyboard builders, `VERBOSE_CALLBACK_PREFIX = "vbs:"`).
- [ ] Add `verbose_picker_runtime.py` mirroring `model_picker_runtime.py`'s shape (open, handle_callback, _edit_*).
- [ ] Register `dispatcher.callback_query(lambda q: (q.data or "").startswith(VERBOSE_CALLBACK_PREFIX))` next to the existing model-picker registration in `bot.py:449-454`.
- [ ] Update the `/verbose` slash-command handler so calling it with no args opens the picker (currently expects an integer arg).
- [ ] Tests in `backend/tests/test_telegram_verbose_picker.py` mirroring `test_telegram_model_picker.py` (label formatting, callback parsing, persistence).
- [ ] Update Telegram docs in `frontend/content/docs/handbook/` if a user-facing reference exists.



## Tracking

- GitHub: https://github.com/OctavianTocan/Pawrrtal-AI/issues/343
