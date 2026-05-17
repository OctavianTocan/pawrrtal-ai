---
# pawrrtal-tfxd
title: Phase 1 — Config & env vars (settings.telegram_*)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:12Z
updated_at: 2026-05-14T19:52:12Z
parent: pawrrtal-l65f
---

## Why

Every later piece reads from these settings: the lifespan gate, the API's
"not configured" 503, the webhook secret check, the deep-link builder. If you
miss `telegram_bot_username`, the frontend has no `t.me/<bot>?start=<code>`
target and falls back to a paste-only UX.

This is the smallest bean — start here to warm up the workflow.

## What to build

File: `backend/app/core/config.py` — add fields to the existing `Settings` class.

Fields (defaults shown — empty strings disable, mode literal):

| Field | Type | Default | Role |
|---|---|---|---|
| `telegram_bot_token` | `str` | `""` | Bot API token from @BotFather. Empty = whole channel off. |
| `telegram_bot_username` | `str` | `""` | Username without `@`. Used to build the deep link. |
| `telegram_mode` | `Literal["polling", "webhook"]` | `"polling"` | Polling for laptops, webhook for prod. |
| `telegram_webhook_url` | `str` | `""` | Public HTTPS URL Telegram POSTs to. Required when mode=webhook. |
| `telegram_webhook_secret` | `str` | `""` | Shared secret echoed in `X-Telegram-Bot-Api-Secret-Token`. |

Plus one Pydantic validator on `telegram_bot_username` (mode=`"before"`) that
strips a leading `@`. Reason: humans paste `@MyBot` from their notes and a deep
link of `t.me/@MyBot?start=...` redirects to the Telegram homepage instead of
the bot.

## Contracts

```
class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_mode: Literal["polling", "webhook"] = "polling"
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""

    @field_validator("telegram_bot_username", mode="before")
    @classmethod
    def _strip_telegram_at_prefix(cls, value):
        if isinstance(value, str):
            return value.lstrip("@")
        return value
```

The validator must run **before** field coercion (`mode="before"`) because
`@` is a valid character — Pydantic won't reject it; you have to strip it.

## Edge cases

- Don't make `telegram_bot_token` required. CI and ephemeral previews have no
  bot. Empty = disabled is the contract every later layer reads.
- `Literal` (not `str`) for `telegram_mode` so a typo like `"poling"` raises at
  config load, not at lifespan boot.
- The validator must handle non-string inputs (env vars are always strings, but
  pydantic-settings may pass `None` for unset values; the `isinstance` guard
  is the simplest safe form).

## Tests that should pass after this

None directly. But you've removed an import error blocker for the downstream
beans. Smoke check:

```bash
cd backend && .venv/bin/python -c "from app.core.config import settings; print(settings.telegram_mode)"
# expect: polling
```

## Next

Bean 2 — database models (the ORM classes for the tables that already exist
in the DB via migrations 007 + 011).
