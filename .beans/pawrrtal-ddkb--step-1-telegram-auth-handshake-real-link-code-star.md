---
# pawrrtal-ddkb
title: 'Step 1 — Telegram auth handshake: real link code + /start binds the user'
status: todo
type: feature
priority: high
created_at: 2026-05-17T18:15:07Z
updated_at: 2026-05-17T18:15:07Z
---

## Where we are today

The bot has no identity for the user. The only handler in
`backend/app/integrations/telegram/bot.py:38` is an echo. Any text in
returns `"Hello, world\! You said: <text>"`. There is no way for the bot
to know which Pawrrtal user is on the other end.

The HTTP endpoint that should hand the user a code returns garbage:
`backend/app/api/channels.py:38` literally returns
`{"code": "TODO", "bot_username": "TODO", "deep_link": "TODO"}`.

The CRUD helper `issue_link_code_service` at
`backend/app/crud/channel.py:55` exists but constructs an empty
`ChannelLinkCode()`, never sets columns, never adds to session, never
commits. Dead code.

And the lifespan at `backend/main.py:63` starts the polling task
unconditionally — with no token, the polling task throws inside
`Bot(token=None)` and dies silently because the task is never awaited
until shutdown.

## What "done" looks like

1. I log in on the web app and `POST /api/v1/channels/telegram/link`
   (curl is fine — no UI work here).
2. The endpoint returns a real one-time code + a `t.me/<bot>?start=<code>`
   deep link.
3. I open the deep link (or send `/start <code>` manually) to my bot.
4. The bot replies `Connected ✅ — you can now chat with Pawrrtal from here.`
5. A row exists in `channel_bindings` with my user_id, the Telegram user
   id, and provider="telegram".
6. The link code row in `channel_link_codes` has `used_at` set.
7. With no `TELEGRAM_BOT_TOKEN` set, the server starts cleanly, logs one
   line saying Telegram is disabled, and serves the rest of the API.

We are NOT chatting with the agent yet. We are only proving the bind
handshake.

## Concrete changes

### 1. `backend/app/crud/channel.py` — make `issue_link_code_service` real

- Module-level constants near the top of the file:
  - `_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"` (no `0/O/1/I/L`
    so support tickets don't argue about what was typed).
  - `_CODE_LENGTH = 8` (≈40 bits — fine for 10-min single-use codes).
  - `LINK_CODE_TTL = timedelta(minutes=10)`.
- Private helpers:
  - `_utcnow()` returning `datetime.now(UTC).replace(tzinfo=None)`
    (naive UTC — matches what the other DateTime columns use).
  - `_hash_code(code)` returning
    `hmac.new(settings.auth_secret.encode(), code.encode(), sha256).hexdigest()`.
    HMAC, not bare SHA — a leaked DB shouldn't let someone grind the
    32^8 alphabet offline.
  - `_generate_code()` returning
    `"".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))`.
    Note `secrets.choice`, not `random.choice`.
- Rewrite `issue_link_code_service` to:
  - Generate a code, hash it, build a `ChannelLinkCode(code_hash=...,
    user_id=..., provider=..., created_at=now, expires_at=now+TTL,
    used_at=None)`.
  - `session.add(row); await session.commit()`.
  - Return `(plaintext_code, expires_at)` — a tuple. The plaintext
    leaves this function exactly once, for the HTTP response. Never
    persisted plaintext anywhere.
- Add a new helper `redeem_link_code(code, provider, external_user_id,
  session) -> ChannelBinding | None`. Returns `None` on EVERY failure
  mode (missing, wrong provider, used, expired) so the bot can show a
  single generic reply that doesn't leak which case it was. Happy path:
  upsert on `(provider, external_user_id)` — if a binding already exists
  for that pair, update its `user_id` to the new one (re-bind path);
  otherwise insert. Mark the code `used_at=now` and commit.

### 2. `backend/app/api/channels.py` — make the link endpoint return real data

At line 38-56, replace the hardcoded `TODO` return with:

- Call `issue_link_code_service(user.id, SURFACE_TELEGRAM, session)` →
  get `(code, expires_at)`.
- Build the deep link as
  `f"https://t.me/{settings.telegram_bot_username}?start={code}"`.
- Return `TelegramLinkCodeRead(code=code, expires_at=expires_at,
  bot_username=settings.telegram_bot_username, deep_link=deep_link)`.

If `settings.telegram_bot_username` doesn't exist yet, add it to
`backend/app/core/config.py` and the env example. Without it the deep
link is useless. The existing token-name guess is `telegram_bot_token`
so follow the same pattern.

### 3. `backend/app/integrations/telegram/bot.py` — add `/start` and guard startup

- Replace the module-level setup. Don't import-time construct
  `Dispatcher()` if the token is missing. Either guard the entire
  module body behind a `if not settings.telegram_bot_token: return`
  early-out in the polling function and skip constructing the
  dispatcher at module scope, OR move dispatcher creation INTO
  `start_telegram_bot_polling`.
- Add the start handler:
  ```python
  from aiogram.filters import CommandStart, CommandObject

  @router.message(CommandStart(deep_link=True))
  async def handle_start(message: Message, command: CommandObject) -> None:
      code = (command.args or "").strip().upper()
      if not code:
          await message.answer(_NOT_BOUND_MESSAGE)
          return
      async with async_session_maker() as session:
          binding = await redeem_link_code(
              code=code,
              provider="telegram",
              external_user_id=str(message.from_user.id),
              session=session,
          )
      if binding is None:
          await message.answer(_BIND_BAD_CODE_MESSAGE)
          return
      await message.answer(_BIND_OK_MESSAGE)
  ```
  Reply strings stay as module constants at the top so future copy
  edits don't require tracing through the dispatcher.
- Keep the existing echo handler for now — Step 2 will replace it.

### 4. `backend/main.py` — gate the polling task

At line 62-63, wrap the task creation:

```python
telegram_polling_task: asyncio.Task[None] | None = None
if settings.telegram_bot_token:
    telegram_polling_task = asyncio.create_task(start_telegram_bot_polling())
else:
    logger.info("TELEGRAM_BOT_TOKEN unset — Telegram bot disabled.")
```

And in the `finally` block, only cancel if the task exists.

## Footguns

- **HMAC key**: `settings.auth_secret` MUST be set in your env. If it
  isn't, the hash is keyed with an empty bytestring — still functional
  but not better than bare SHA. The startup should already fail if it's
  missing; verify.
- **Case sensitivity**: codes are uppercase. Upper the input in the
  handler so a user typing lowercase still binds.
- **External user id type**: `message.from_user.id` is an int.
  `ChannelBinding.external_user_id` is `String(128)`. Stringify it on
  insert AND on lookup — mixing types means the index miss.
- **`Bot(token=None)`**: don't let this run. The whole point of the
  guard.
- **`scalar_one_or_none` on binding lookup**: without a unique
  constraint on `(provider, external_user_id)`, two rebinds could create
  duplicates and crash future queries. Add a `UniqueConstraint` to
  `ChannelBinding.__table_args__` and an Alembic migration in the same
  commit.

## Out of scope

- No LLM. No agent. No channel adapter. No streaming.
- No `/stop`, `/new`, `/model`, `/verbose`.
- No frontend UI for the connect button — curl is fine.
- No webhook mode.
- No forum-topic handling.

## How to test it

1. `just dev` with `TELEGRAM_BOT_TOKEN` set in your backend env.
2. Confirm the server boots cleanly with both a real token and no
   token (twice).
3. With dev cookies for a logged-in user:
   `curl -X POST http://localhost:8000/api/v1/channels/telegram/link
   -b "$(cat cookies.txt)"`. Expect JSON with a non-TODO `code` and a
   real deep link.
4. Open the deep link, hit Start. Expect "Connected ✅".
5. Verify a row in `channel_bindings` and a `used_at`-marked row in
   `channel_link_codes`.
6. Run it again with the same code — expect the generic "didn't work"
   message.
7. Run with an expired code (manually set `expires_at` in past) — same
   generic message.
