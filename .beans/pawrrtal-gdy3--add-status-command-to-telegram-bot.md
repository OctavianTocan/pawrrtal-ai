---
# pawrrtal-gdy3
title: Add /status command to Telegram bot
status: completed
type: feature
priority: normal
created_at: 2026-05-17T17:03:41Z
updated_at: 2026-05-17T17:10:50Z
---

Slash command that returns bot uptime (this worker) + active conversation summary: model, verbose level, started-at, message counts, token totals, run status. Helpers: get_bot_uptime_seconds, is_run_active, get_conversation_status.

## Summary of Changes

Added `/status` slash command to the Telegram bot. Replies immediately with a compact gateway + conversation snapshot.

**Reply shape (Telegram HTML, no `<pre>`):**
```
📊 Pawrrtal gateway

⏱  Bot up: 4h 12m (this worker)
🤖 Model: Sonnet 4.6 (<code>...</code>)
🔊 Verbose: 1 (normal)

💬 This conversation
   • Started: 2h 03m ago
   • Messages: 14 (7 yours, 7 assistant)
   • Tokens: 18,420 in / 6,108 out
   • Status: idle
```
Plus a conditional `🧵 Topic thread: <id>` line for chats inside Telegram topics, and a `⚠️ catalog lookup failed` suffix on the model line when the stored `model_id` isn't in the catalog.

**Touched files:**
- `backend/app/crud/conversation.py` — new `ConversationStatus` dataclass + `get_conversation_status()` aggregating per-role message counts (from `chat_messages`) and per-turn token totals (from `cost_ledger.input_tokens`/`output_tokens`).
- `backend/app/integrations/telegram/handlers.py` — `handle_status_command` plus pure formatters (`_format_duration`, `_format_token_count`, `_format_model_display`, `_render_status_message`). The handler takes `bot_uptime_seconds` and `is_chat_run_active` as parameters so it stays a pure function over its inputs.
- `backend/app/integrations/telegram/bot.py` — `_BOT_START_MONOTONIC` module-level constant, `get_bot_uptime_seconds()` and `is_chat_run_active(chat_id)` helpers, added `("status", ...)` to `_TELEGRAM_COMMANDS`, and wired the `@dispatcher.message(Command("status"))` branch.
- `backend/tests/test_telegram_channel.py` — 10 new tests covering the formatters, the renderer (known model, unknown model warning, topic thread line), and the handler (unbound nudge + bound happy path with run-active=true). Updated the command-menu assertion to include `status`.

**Out of scope per brainstorm decisions:**
- No catalog change for context_window — raw token counts only.
- Multi-worker uptime caveat noted in code ("(this worker)"); not promoted to a shared store.
- No cost/USD line; no rate-limit/error counters.

**Verified:** `uv run ruff check` clean across `app/` + `tests/`, `uv run pytest` 790 passed / 1 skipped.
