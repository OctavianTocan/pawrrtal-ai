---
# pawrrtal-w8xp
title: Phase 8 — Framework-thin handlers (/start /stop /new /model plain text)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:13Z
updated_at: 2026-05-14T19:52:13Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-bn6c
---

## Why

Handlers are the **framework-thin** layer between aiogram and the core. The
design rule: **no aiogram imports in this file**. Every handler takes a plain
dataclass (`TelegramSender`) and a `session`, and returns either a string
reply or a `TelegramTurnContext`.

This split is what makes the handler tests possible — they call the handlers
directly with a fabricated `TelegramSender`, no bot, no aiogram, no asyncio
machinery. Read `tests/test_telegram_channel.py` for the call shape.

## What to build

File: `backend/app/integrations/telegram/handlers.py`. Also recreate the
package: `backend/app/integrations/telegram/__init__.py` (re-exports for
bean 11).

### Module constants

```
PROVIDER = "telegram"

# 8 uppercase chars from the look-alike-free alphabet (matches the CRUD
# alphabet — codes can be entered case-insensitively but we upper before
# comparing)
_CODE_SHAPE = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8}$")

# Reply copy lives at module scope so review = read this file
_NOT_BOUND_MESSAGE      = "Hey 👋 I don't recognize this Telegram account yet.\n\n..."
_BIND_OK_MESSAGE        = "Connected ✅ — you can now chat with Nexus from here."
_BIND_BAD_CODE_MESSAGE  = "That code didn't work. It may have expired ... or already been used."
_STOP_STOPPED_MESSAGE   = "⏹ Stopped."
_STOP_NOTHING_MESSAGE   = "Nothing is running right now."
_MODEL_MISSING_MESSAGE  = "Usage: /model <vendor>/<model>\n\n..."   # HTML-escape angle brackets
_MODEL_INVALID_MESSAGE  = "Couldn't parse <code>{raw}</code> as a model ID ({reason})..."
_MODEL_NOT_BOUND_MESSAGE = "You need to connect your account first before switching models."
_MODEL_OK_MESSAGE       = "Model switched to <code>{model_id}</code> ✅"
_MODEL_FAIL_MESSAGE     = "Couldn't update model — please try again."
_NEW_NOT_BOUND_MESSAGE  = "Connect your account first before starting a new conversation."
_NEW_OK_MESSAGE         = "✨ New conversation started. What's on your mind?"
```

Bot uses `ParseMode.HTML` (set in bean 11), so use `&lt;` for literal `<` in
copy.

### Dataclasses

Both frozen — they're value objects passed across the framework boundary.

```
@dataclass(frozen=True)
class TelegramSender:
    user_id: int           # Telegram numeric user id
    chat_id: int
    username: str | None
    full_name: str | None
    thread_id: int | None = None    # Bot API 9.3+ topic thread

@dataclass(frozen=True)
class TelegramTurnContext:
    nexus_user_id: uuid.UUID         # resolved from channel_bindings
    conversation_id: uuid.UUID       # the Telegram-scoped conversation
    model_id: str                    # conv override or catalog default
    thread_id: int | None = None     # forwarded from sender
```

### Handler 1 — `handle_start_command`

Signature: `async (*, sender, payload, session) -> str`.

```
code <- (payload or "").strip()
if not code:
    return _NOT_BOUND_MESSAGE       # bare /start, no deep link

binding <- await redeem_link_code(
    code, PROVIDER,
    external_user_id=str(sender.user_id),
    external_chat_id=str(sender.chat_id),
    display_handle=sender.username or sender.full_name,
    session=session,
)
if binding is None:
    return _BIND_BAD_CODE_MESSAGE   # expired / already used / cross-provider
return _BIND_OK_MESSAGE
```

Note: log the success with `external_user_id` and `nexus_user_id` for
binding traces — never log the code itself.

### Handler 2 — `handle_plain_message` (the main one)

Signature: `async (*, sender, text, session) -> str | TelegramTurnContext`.

```
nexus_user_id <- await get_user_id_for_external(PROVIDER, str(sender.user_id), session)

if nexus_user_id is None:
    # Auto-redeem shortcut: the unbound nudge tells users to "send me your code"
    # so if a plain message is exactly the code shape, try redemption here too
    candidate <- text.strip().upper()
    if _CODE_SHAPE.fullmatch(candidate):
        binding <- await redeem_link_code(code=candidate, PROVIDER, ..., session)
        return _BIND_OK_MESSAGE if binding else _BIND_BAD_CODE_MESSAGE
    return _NOT_BOUND_MESSAGE

# Bound user — route to LLM
conversation <- await get_or_create_telegram_conversation_full(
    user_id=nexus_user_id, session=session, thread_id=sender.thread_id,
)
model_id <- conversation.model_id or default_model().id

return TelegramTurnContext(
    nexus_user_id=nexus_user_id,
    conversation_id=conversation.id,
    model_id=model_id,
    thread_id=sender.thread_id,
)
```

**Why upper before regex**: the user might type the code lowercase. The
alphabet is uppercase-only; uppering normalizes before matching.

**Why auto-redeem only on exact shape**: arbitrary chatter from an unbound
user shouldn't try to redeem as a code — only the precise 8-char pattern.

### Handler 3 — `handle_new_command`

Signature: `async (*, sender, session) -> str`.

```
nexus_user_id <- await get_user_id_for_external(PROVIDER, str(sender.user_id), session)
if nexus_user_id is None:
    return _NEW_NOT_BOUND_MESSAGE

conv <- Conversation(
    id=uuid4(), user_id=nexus_user_id, title="Telegram",
    origin_channel="telegram", telegram_thread_id=sender.thread_id,
    created_at=now, updated_at=now,
)
session.add(conv)
await session.commit()
return _NEW_OK_MESSAGE
```

**Why not `get_or_create_*` here?** `/new` is explicitly "start a fresh
conversation"; it must always insert a new row even when one already exists.
Topic-scoped: `telegram_thread_id` is preserved so the new conversation stays
in the same topic the user typed `/new` from.

### Handler 4 — `handle_stop_command` (sync!)

Signature: `def (*, was_running: bool) -> str` (no `async`, no `session`).

```
return _STOP_STOPPED_MESSAGE if was_running else _STOP_NOTHING_MESSAGE
```

The **actual cancellation** happens in `bot.py` (bean 11) which owns the
`_running_tasks` dict. This handler just returns the right reply string.

### Handler 5 — `handle_model_command`

Signature: `async (*, sender, model_arg, session) -> str`.

```
raw <- model_arg.strip()
if not raw:
    return _MODEL_MISSING_MESSAGE

try:
    parsed <- parse_model_id(raw)             # structural parser, NOT catalog check
except InvalidModelId as exc:
    return _MODEL_INVALID_MESSAGE.format(raw=raw, reason=str(exc))

nexus_user_id <- await get_user_id_for_external(PROVIDER, str(sender.user_id), session)
if nexus_user_id is None:
    return _MODEL_NOT_BOUND_MESSAGE

conv <- await get_or_create_telegram_conversation_full(
    user_id=nexus_user_id, session=session, thread_id=sender.thread_id,
)

canonical_id <- parsed.id          # always "host:vendor/model" form
updated <- await update_conversation_model(conv.id, canonical_id, session)
if not updated:
    return _MODEL_FAIL_MESSAGE
return _MODEL_OK_MESSAGE.format(model_id=canonical_id)
```

**Why structural-only parsing (not catalog validation)**: per ADR
`2026-05-14-model-id-canonical-format-and-backend-catalog.mdx`, the `/model`
command is catalog-ignorant. If the user picks a parseable-but-unknown model,
they only find out on the **next chat turn** when the auto-clear safety net
fires (bean 11's `_resolve_provider_with_auto_clear`). There's a deferred
bean (`pawrrtal-yea3`) to add proactive catalog validation here.

**Why store canonical_id, not raw**: keeps stored model IDs consistent
regardless of whether the user typed the host prefix. The catalog uses
canonical form for lookups.

## Edge cases

- `display_handle = sender.username or sender.full_name` — Telegram lets
  users have neither (rare); persist `None` in that case.
- Auto-redeem uppercases first: `candidate = text.strip().upper()`. Some users
  paste the code with surrounding spaces from email.
- The handlers must **never** import from `aiogram`. The whole point of this
  layer is that the tests can call them with hand-rolled `TelegramSender`
  dataclasses. If you need aiogram (for sending), that's bean 11's job.
- `handle_stop_command` is sync. Don't add `async` "for consistency" — the
  call site in `bot.py` is sync after the task cancellation.
- Use `re.fullmatch`, not `re.match`, for the code shape. `match` only
  anchors at the start.

## Tests that should pass after this

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_telegram_channel.py::TestHandlePlainMessage \
  tests/test_telegram_channel.py::TestHandleStopCommand \
  tests/test_telegram_channel.py::TestHandleModelCommand \
  tests/test_channels_api.py \
  -x
```

The test_channels_api.py tests exercise both the API (bean 4) AND the handlers
together — they construct fake updates and assert the reply strings. They all
go green after this bean.

## Next

Bean 9 — the turn streaming wrapper. This stitches together persistence,
history fetch, provider stream, and the `TelegramChannel.deliver` loop you
built in bean 5.
