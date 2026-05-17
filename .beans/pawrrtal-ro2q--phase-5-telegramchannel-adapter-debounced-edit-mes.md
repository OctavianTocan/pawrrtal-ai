---
# pawrrtal-ro2q
title: Phase 5 — TelegramChannel adapter (debounced edit_message_text delivery)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:12Z
updated_at: 2026-05-14T19:52:12Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-1irw
---

## Why

The `TelegramChannel` adapter is what makes Telegram **look the same** as web
to the core. It implements the same `Channel` protocol that `SSEChannel` does
— but where SSE yields newline-framed JSON bytes, Telegram delivers entirely
by side effect: it edits a placeholder message progressively as deltas arrive.

The signature has to stay `AsyncIterator[bytes]` (protocol's common
denominator), so it's an async generator that yields nothing. The caller
drives it with `async for _ in channel.deliver(stream, msg): pass`.

## Telegram flood-control reality

Telegram allows ~20 message edits per minute per chat (~one every 3 seconds).
Spam edits and you get throttled, and the rate-limit response cascades through
aiogram in ways that are painful to handle. So you debounce.

Two debounce axes — emit an edit when **either** condition trips:

- `_EDIT_DEBOUNCE_CHARS = 40` new characters have accumulated since the last edit
- `_MAX_EDIT_INTERVAL_S = 3.0` seconds have elapsed since the last edit

Plus a hard message ceiling: `_MAX_MESSAGE_LEN = 4096`. Telegram refuses
anything longer. Truncate with `…` — splitting into multiple messages is future
work (the placeholder is a single `message_id` and `edit_message_text` can't
target multiple).

## What to build

File: `backend/app/channels/telegram.py`.

```
SURFACE_TELEGRAM = "telegram"
_EDIT_DEBOUNCE_CHARS = 40
_MAX_EDIT_INTERVAL_S = 3.0
_MAX_MESSAGE_LEN = 4096
```

### `class TelegramChannel`

Implements the `Channel` protocol from `backend/app/channels/base.py`:

```
class TelegramChannel:
    surface: str = SURFACE_TELEGRAM

    async def deliver(self, stream, message):
        # message["metadata"] keys (validated by contract, not by code):
        #   "bot":        aiogram.Bot
        #   "chat_id":    int | str
        #   "message_id": int   <- the "⏳" placeholder to overwrite
        ...
```

Stateless singleton — registered once in the channel registry (bean 7), shared
across every Telegram turn.

### `deliver` pseudocode

```
meta       <- message["metadata"]
bot        <- meta["bot"]
chat_id    <- meta["chat_id"]
message_id <- meta["message_id"]

accumulated      <- ""
chars_since_edit <- 0
last_edit_at     <- asyncio.get_event_loop().time()

async for event in stream:
    if event.type != "delta":          # ignore tool_call/tool_result/done/error
        continue
    chunk            <- event["content"]
    accumulated      += chunk
    chars_since_edit += len(chunk)

    now     <- loop_time()
    elapsed <- now - last_edit_at

    if (chars_since_edit >= 40 or elapsed >= 3.0) and accumulated:
        await _safe_edit(bot, chat_id, message_id, accumulated)
        chars_since_edit <- 0
        last_edit_at     <- now

# Final flush — guarantee the user sees the full reply even if the last
# delta didn't cross either threshold
if accumulated:
    await _safe_edit(bot, chat_id, message_id, accumulated)

# Required: bare yield to make this an async generator. Unreachable but
# the type signature is AsyncIterator[bytes].
return
yield  # noqa
```

### `async def _safe_edit(bot, chat_id, message_id, text)`

```
if len(text) > 4096:
    text = text[:4095] + "…"

try:
    await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
except Exception as exc:
    if "not modified" in str(exc).lower():
        return                # benign — model emitted an empty delta
    logger.warning("TELEGRAM_EDIT_FAILED chat_id=%s message_id=%s error=%s",
                   chat_id, message_id, exc)
    # DO NOT re-raise — partial response beats silent failure
```

Why catch `Exception` and only swallow `not modified`: aiogram's exception
hierarchy varies between versions and we don't want a string-shape change to
break delivery. Any other error gets logged and the loop continues — the user
sees whatever did get edited in.

## Why this design

- **Char-debounce, not time-only**: A model that emits tokens fast would
  produce 20 edits/second with a pure time debounce. Char-growth flattens
  the rate.
- **Time-debounce, not char-only**: A model that emits one slow token at a
  time would never trip a char threshold; the time bound guarantees liveness.
- **Final flush mandatory**: The last delta is almost always smaller than 40
  chars. Without the final flush, users see a half-finished reply.
- **`accumulated` is the full message every edit** — `edit_message_text`
  takes the *replacement* text, not a delta. Telegram has no "append" API.

## Edge cases

- `event.get("type")` — defensive read; provider streams should always have
  `type` but be paranoid.
- `chunk` may be empty (`""`) — that's fine, `len("") == 0` doesn't trip the
  threshold and `accumulated += ""` is a no-op.
- Non-delta events (`tool_call`, `tool_result`, `done`, `error`): the channel
  ignores them. The turn-streaming wrapper (bean 9) handles those via the
  `ChatTurnAggregator` separately for persistence.
- Cancellation (`asyncio.CancelledError` from `/stop`): the loop is at an
  `await` point inside `_safe_edit` → exception propagates → `finally` in
  the turn wrapper finalizes the assistant row with `status="failed"`. Don't
  catch `CancelledError` here.
- `loop.time()` is monotonic — never goes backwards even if system clock
  changes. Don't use `time.time()`.

## Tests that should pass after this

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_telegram_channel.py::TestTelegramChannelSurface \
  tests/test_telegram_channel.py::TestTelegramChannelDeliver \
  -x
```

The `TestTelegramRegistry` tests still fail (bean 7).

## Next

Bean 6 — `make_telegram_sender`, the MIME-routed factory that wires Telegram
into the channel-agnostic `send_message` AgentTool.
