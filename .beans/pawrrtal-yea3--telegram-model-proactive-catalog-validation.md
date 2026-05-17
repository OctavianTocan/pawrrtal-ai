---
# pawrrtal-yea3
title: 'Telegram /model: proactive catalog validation'
status: completed
type: feature
priority: low
created_at: 2026-05-14T06:00:42Z
updated_at: 2026-05-17T09:57:54Z
---

Add catalog.is_known() check at /model time so Telegram users discover unknown-but-well-formed model IDs immediately, instead of on their next chat turn (which currently triggers the UnknownModelId auto-clear path designed in ADR 2026-05-14). The auto-clear behaviour is the correctness safety net; this is the UX upgrade on top. See frontend/content/docs/handbook/decisions/2026-05-14-model-id-canonical-format-and-backend-catalog.md §7.



Completed 2026-05-17: handle_model_command now validates parsed IDs against MODEL_CATALOG with catalog.find(parsed). Unknown-but-well-formed IDs return a clear catalog error immediately and do not write Conversation.model_id. Covered by backend/tests/test_telegram_channel.py.
