---
# pawrrtal-o7xf
title: 'feat(channels): POST /api/v1/channels/telegram/simulate — synthetic update endpoint'
status: todo
type: feature
priority: normal
created_at: 2026-05-28T09:14:50Z
updated_at: 2026-05-28T09:14:50Z
---

From paw v3 brainstorm Thread 4. Backend currently has no way to inject a synthetic Telegram update from outside the real webhook. Add a dev-only POST that accepts {text, chat_id, reply_to?} and pushes through the same handler the webhook uses. Gated on settings.telegram_simulate_enabled (off in prod). Unlocks paw verify telegram --simulate for the full link → message → reply → DB-row chain. Companion paw work: paw channels simulate-update --text 'X'.
