---
# pawrrtal-uppe
title: Telegram /model command — switch model for current conversation
status: completed
type: feature
priority: normal
created_at: 2026-05-07T16:18:07Z
updated_at: 2026-05-17T09:57:44Z
---

## Goal

Add a ``/model`` command in the Telegram bot that switches the active model for the user's Telegram-bound conversation. Format: ``/model provider/model``, e.g. ``/model gemini/gemini-3-flash-preview`` or ``/model claude/claude-sonnet-4-6``.

## Acceptance

- ``/model`` (no argument) replies with the current model and a list of valid options scoped by allowed providers.
- ``/model gemini/gemini-3-flash-preview`` updates the conversation row's ``model_id`` and replies with a confirmation.
- An invalid format (no ``/``, unknown provider, unknown model for that provider) replies with a clear error and the valid format.
- The next plain message uses the new model.
- Setting the model only affects the current Telegram-bound conversation; other conversations (web app) are unaffected.

## Where to wire it

- ``backend/app/integrations/telegram/handlers.py`` already has ``handle_start_command``. Add a sibling ``handle_model_command`` that takes the same ``sender`` + ``payload`` shape.
- Dispatcher in ``backend/app/integrations/telegram/bot.py`` routes ``/start`` today; add ``/model`` to the same dispatch.
- Conversation row already has a ``model_id`` field used by ``handle_plain_message``'s ``TelegramTurnContext`` — update it via a CRUD helper.
- The list of valid provider/model pairs should come from the same registry used by the new model-list API endpoint (see related bean for backend-driven model list).

## Tests

- ``/model`` with no payload → returns current + list.
- Valid payload → row updated, ack sent.
- Invalid payload variants → clear error, no DB write.
- Cross-conversation isolation (Telegram conv updated, web conv untouched).

## Todos

- [ ] Build a CRUD helper to update conversation ``model_id`` for a Telegram-bound user (resolve user → default Telegram conv via existing helper)
- [ ] Add ``handle_model_command`` to ``handlers.py``
- [ ] Wire dispatch in ``bot.py``
- [ ] Validate ``provider/model`` against the registry
- [ ] Reuse the new model-list registry once the related bean lands
- [ ] Tests covering the four acceptance cases above

## Related

- Depends on the model-registry bean for the source of truth on valid models



Session update 2026-05-17: Implementing Telegram inline model picker based on OpenClaw's provider -> paged model selection pattern. Keep typed /model <id> support, add /models, and make /model with no argument open the picker.



Completed 2026-05-17: Added /models and /model-without-argument inline picker using the backend MODEL_CATALOG. Picker opens provider buttons, paginates models, marks the active model, and writes the selected canonical model_id through the existing Telegram /model update path. Also added proactive catalog validation for typed /model values so unknown-but-well-formed IDs are rejected immediately. Tests added in backend/tests/test_telegram_model_picker.py and backend/tests/test_telegram_channel.py.
