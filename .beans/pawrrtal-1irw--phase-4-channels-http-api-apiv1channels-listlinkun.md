---
# pawrrtal-1irw
title: Phase 4 — Channels HTTP API (/api/v1/channels — list/link/unlink/webhook)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:12Z
updated_at: 2026-05-14T19:52:12Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-ei4l
---

## Why

This is the Settings UI's only seam to the channel. The frontend
(`frontend/lib/channels.ts`) calls four endpoints; the bot doesn't. The
`POST .../link` returns 503 when the bot is unconfigured — the frontend hook
turns that into a "ask your operator" panel instead of an error.

Also lives here: the **webhook intake** for production mode. Polling deployments
never hit it; webhook deployments depend on it for every Telegram update.

## What to build

File: `backend/app/api/channels.py`. Mounted at `/api/v1/channels`.

Two re-added Pydantic schemas in `backend/app/schemas.py`:

```
class ChannelBindingRead(BaseModel):
    provider: str
    external_user_id: str
    external_chat_id: str | None = None
    display_handle: str | None = None
    created_at: datetime

class ChannelLinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    bot_username: str | None = None
    deep_link: str | None = None
```

These are public response shapes — keep them stable. The frontend reads them.

### Module helpers (private)

```
_TELEGRAM = "telegram"

def _telegram_configured() -> bool:
    # Both fields required: token to talk to the API, username to build deep links
    return bool(settings.telegram_bot_token and settings.telegram_bot_username)

def _build_deep_link(code: str) -> str | None:
    if not settings.telegram_bot_username:
        return None
    # URL-encode the code in case future alphabets include unsafe chars
    return f"https://t.me/{settings.telegram_bot_username}?start={quote(code)}"
```

### Routes

`get_channels_router()` returns an `APIRouter(prefix="/api/v1/channels", tags=["channels"])`.
All routes require `Depends(get_allowed_user)` — uses the same email-allowlist
gate as the rest of the app.

#### `GET /` — `list_channels`

```
rows <- await list_bindings(user_id=user.id, session=session)
return [ChannelBindingRead(...) for row in rows]
```

Used by `useTelegramBinding`'s 2-second poll while a code is pending.

#### `POST /telegram/link` — `link_telegram`

```
if not _telegram_configured():
    raise HTTPException(503, detail="Telegram channel is not configured. "
                                     "Set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME in .env.")
code, expires_at <- await issue_link_code(user.id, _TELEGRAM, session)
return ChannelLinkCodeResponse(code, expires_at, bot_username, deep_link=_build_deep_link(code))
```

The 503 is the contract the frontend depends on — `useTelegramBinding` catches
that exact status and flips into the "not configured" UI branch.

#### `DELETE /telegram/link` — `unlink_telegram`

```
await delete_binding(user.id, _TELEGRAM, session)
# return 204 even when there was no binding — idempotent
```

Return type is `None`, decorator `status_code=204`. The Settings UI hits this
on every "Disconnect" click without first checking state.

#### `POST /telegram/webhook` — `telegram_webhook`

This route is hit by **Telegram**, not the user. `include_in_schema=False` so
OpenAPI doesn't expose it. Use a `Header(default=None)` dependency for
`x_telegram_bot_api_secret_token` (FastAPI auto-maps the dashes).

```
service <- getattr(request.app.state, "telegram_service", None)
if service is None or settings.telegram_mode != "webhook":
    raise HTTPException(404, detail="Telegram webhook is not enabled on this deployment.")
if settings.telegram_webhook_secret \
   and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
    raise HTTPException(403, detail="Bad webhook secret.")

from aiogram.types import Update      # local import; aiogram stays out of the import graph for polling
body   <- await request.json()
update <- Update.model_validate(body)
await service.feed_webhook_update(update)
# return 204
```

Two safety properties:

1. **Mode gate first**: even with a perfectly forged secret, if the deployment
   is in polling mode the route 404s. Belt-and-suspenders.
2. **Constant-time-ish comparison**: secret comparison with `!=` is fine here
   because the secret is server-side state, not user-typed — no timing oracle
   to exploit. Don't bother with `hmac.compare_digest` for this.

## Why the bot doesn't talk to these routes

The bot adapter calls `app/crud/channel.py` directly (same process, same DB
session). HTTP would be pure overhead. The HTTP layer exists for the **web
frontend** and for **Telegram's webhook callback**. Two different consumers.

## Edge cases

- Don't accept a `provider` query param on `GET /`. List all bindings the
  user owns; frontend filters by `provider === "telegram"`.
- Don't 401 on missing webhook secret if the operator hasn't configured one.
  The `if settings.telegram_webhook_secret and ...` guard means "only check
  when configured". Operators who skip the secret get an open webhook —
  warn them in `docs/`, but don't force-enable.
- Return `ChannelLinkCodeResponse.deep_link = None` when `bot_username` is
  unset, **not** an empty string. The frontend renders the "Open Telegram"
  button conditionally on truthiness.

## Wire it into main.py

In `backend/main.py`:

```
from app.api.channels import get_channels_router
...
fastapi_app.include_router(get_channels_router())
```

The deletion left a comment marker where to put it back.

## Tests that should pass after this

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_channels_api.py::test_link_returns_503_when_telegram_unconfigured \
  tests/test_channels_api.py::test_link_issues_code_with_deep_link \
  tests/test_channels_api.py::test_list_channels_starts_empty \
  tests/test_channels_api.py::test_unlink_is_idempotent \
  -x
```

The other tests in `test_channels_api.py` (`*_redeem_*`, `*_plain_message_*`,
`*_unbind_removes_binding`) exercise the **handlers** — they'll go green after
bean 8.

## Next

Bean 5 — the `TelegramChannel` adapter. This is the side-effect-only `deliver`
loop that turns provider stream events into `bot.edit_message_text` calls.
