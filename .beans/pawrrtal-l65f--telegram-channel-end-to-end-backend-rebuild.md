---
# pawrrtal-l65f
title: 'Telegram channel: end-to-end backend rebuild'
status: todo
type: epic
priority: high
created_at: 2026-05-14T19:44:45Z
updated_at: 2026-05-14T19:44:45Z
---

## What this is

A from-scratch rebuild of the Telegram channel backend in the
`octavian/practice-telegram` branch. The frontend (`frontend/features/channels/`,
`frontend/lib/channels.ts`) and the full backend test suite are intact — the
tests are your spec. The implementation files for the bot, channel adapter,
channels CRUD, channels HTTP API, and the related ORM models / schemas were
intentionally deleted on this branch.

The branch state right now:

- `backend/app/integrations/telegram/` — **deleted** (whole dir)
- `backend/app/channels/telegram.py` — **deleted**
- `backend/app/api/channels.py` — **deleted**
- `backend/app/crud/channel.py` — **deleted**
- `backend/app/models.py` — `ChannelBinding` + `ChannelLinkCode` classes removed;
  3 conversation columns (`origin_channel`, `telegram_thread_id`, `title_set_by`)
  bindings removed (the DB columns themselves stay — migration 011 still applies).
- `backend/app/schemas.py` — `ChannelBindingRead` + `ChannelLinkCodeResponse` removed.
- `backend/app/channels/__init__.py` + `registry.py` — Telegram export + registration removed.
- `backend/main.py` — `telegram_lifespan` import, lifespan wrapper, and `get_channels_router`
  registration removed.

Migrations `007_add_channel_bindings_and_link_codes` and
`011_add_channel_columns_and_attachment` are untouched. The database schema is
already correct; you only need to rewrite the Python that reads/writes it.

## What the rebuild has to satisfy

Backend test files that must turn green at the end:

- `backend/tests/test_channels.py` — protocol + registry + SSE delivery (only the
  Telegram-registry tests fail now; SSE bits already pass).
- `backend/tests/test_channels_api.py` — link / unlink / list / redeem / replay /
  nudge / ack / unbind.
- `backend/tests/test_telegram_channel.py` — surface, registry, deliver, handlers,
  `/stop`, `/model`, and the auto-clear safety net.
- `backend/tests/test_send_message_tool.py` — `TestMakeTelegramSender` exercises
  the MIME-routed media factory; the rest exercises the channel-agnostic tool.

The frontend hook (`useTelegramBinding`) polls `GET /api/v1/channels` every 2
seconds while a code is pending and expects the same `ChannelBindingRead` shape.
Keep the shape stable.

## Architecture (don't lose sight of this while building)

```
              ┌───────── inbound ───────┐
   Telegram ──►  aiogram Dispatcher     │     ┌─ TelegramSender / TurnContext (handlers.py)
   Update      (polling OR webhook)    ─┴────►│  framework-thin, returns str | TurnContext
                                              │
                                              ▼
                                    ┌─ /start / /stop / /new / /model / plain text
                                    │   • binding CRUD     • model parse
                                    │   • auto-redeem code • cancel asyncio.Task
                                    │
                                    ▼  (turn context only)
                                    _run_llm_turn (bot.py)
                                    ├── resolve provider (auto-clear on bad model)
                                    ├── load workspace + system prompt + tools
                                    ├── stream_persisted_turn (turn_stream.py)
                                    │   ├── fetch last 20 msgs
                                    │   ├── insert user + assistant placeholder
                                    │   ├── _guarded_stream(provider.stream(...))
                                    │   ├── TelegramChannel.deliver  ─► edit_message_text
                                    │   └── finalize_assistant_message (always, in finally)
                                    └── _maybe_set_auto_title (fires once)
```

Build it bottom-up: env → tables → CRUD → API → channel adapter → handlers →
turn streaming → bot lifecycle. Every bean has a *Tests that should pass after
this* section so you can drip-feed `pytest` while you go.

## Resources

- `docs/project-overview.html` — sections "End-to-end chat turn flow" and
  "Conversation Sync (Telegram ↔ Web)" have the canonical state diagrams.
- `docs/deployment/demo-mode.md` — why the bot must be locked off when
  `DEMO_MODE=true`.
- Alembic migrations `007_*` and `011_*` are your schema reference.
- `aiogram` 3.x is the Telegram SDK. `Bot`, `Dispatcher`, polling, webhook,
  `feed_webhook_update`, `edit_message_text`, `edit_forum_topic`.

## How to use the child beans

Each child bean is a **single phase**. They are chained via `blocked-by`, so
`beans list --ready` will surface exactly one task at a time as you finish each
phase. The order matters — later phases assume earlier phases exist.

Each child bean has:

- **Why** — what this layer is for, in plain English.
- **What to build** — file paths + symbol names.
- **Contracts** — data shapes, function signatures, return types.
- **Pseudocode** — algorithmic skeletons (no copy-pasteable code).
- **Edge cases** — the gotchas the prior implementation paid for.
- **Tests that should pass after this** — exact test selectors.
- **Next** — pointer to the next bean.

Pace yourself. Bean 1 is 5 minutes; bean 9 (turn streaming) takes longer.
The point isn't speed — it's that you internalize the seam between provider,
channel, persistence, and dispatcher.
