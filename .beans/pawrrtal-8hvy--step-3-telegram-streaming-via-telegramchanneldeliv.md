---
# pawrrtal-8hvy
title: Step 3 — Telegram streaming via TelegramChannel.deliver (debounced edits)
status: todo
type: feature
priority: high
created_at: 2026-05-17T18:17:00Z
updated_at: 2026-05-17T18:17:00Z
blocked_by:
    - pawrrtal-unt9
---

## Where we are after Step 2

Bot binds users, looks them up, runs the agent, persists messages,
replies with one final Telegram message at the end of each turn. Works,
but feels dead — long responses sit there for 10+ seconds with only a
typing indicator. We want the "watch it stream" UX everywhere else
already has.

`TelegramChannel.deliver()` at `backend/app/channels/telegram.py:34` is
still the noop stub from when the practice rebuild started:

```python
async def deliver(self, stream, message):
    return
    yield
```

And `__init__` at line 26 is `pass` — never stores the surface parameter.

## What "done" looks like

1. I send a question to the bot.
2. Within ~500ms the bot sends a single placeholder message (e.g. `⏳`).
3. As the LLM streams tokens, that SAME message updates in place. I
   can see the response grow.
4. The first edit appears within 1–3 seconds of sending. Subsequent
   edits roughly every 3 seconds OR every ~40 new characters,
   whichever trips first.
5. When the stream finishes, the message contains the full response —
   no truncation if it fits in 4096 chars.
6. If the response exceeds 4096 chars, the final edit ends with `…`
   and the rest is dropped (splitting is a future concern).
7. Telegram's flood-control never trips on a normal-length response.
8. Web app still shows the same conversation with the persisted user +
   final assistant message after the turn completes.

## Concrete changes

### 1. `backend/app/channels/telegram.py` — implement `deliver`

Replace the file's class body. Final shape:

```python
import asyncio
import logging
from collections.abc import AsyncIterator

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.channels.base import Channel, ChannelMessage
from app.core.providers.base import StreamEvent

logger = logging.getLogger(__name__)

SURFACE_TELEGRAM = "telegram"

# Two debounce axes — emit an edit when EITHER trips.
_EDIT_DEBOUNCE_CHARS = 40       # at most ~one edit per 40 new chars
_MAX_EDIT_INTERVAL_S = 3.0      # at least one edit every 3 seconds
_MAX_MESSAGE_LEN = 4096         # Telegram's hard ceiling per message
_TRUNCATION_SUFFIX = "…"


class TelegramChannel(Channel):
    surface: str = SURFACE_TELEGRAM

    def __init__(self, surface: str = SURFACE_TELEGRAM) -> None:
        self.surface = surface     # actually store it this time

    async def deliver(
        self,
        stream: AsyncIterator[StreamEvent],
        message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        meta = message["metadata"]
        bot: Bot = meta["bot"]
        chat_id = meta["chat_id"]
        message_id = meta["message_id"]

        accumulated = ""
        chars_since_edit = 0
        last_edit_at = asyncio.get_event_loop().time()

        async for event in stream:
            if event.get("type") \!= "delta":
                continue
            chunk = event.get("content", "")
            if not chunk:
                continue
            accumulated += chunk
            chars_since_edit += len(chunk)

            now = asyncio.get_event_loop().time()
            elapsed = now - last_edit_at

            if (chars_since_edit >= _EDIT_DEBOUNCE_CHARS or
                    elapsed >= _MAX_EDIT_INTERVAL_S):
                await _safe_edit(bot, chat_id, message_id, accumulated)
                chars_since_edit = 0
                last_edit_at = now

        # Guaranteed final flush so the user sees the complete reply
        # even if the last delta didn't cross either threshold.
        if accumulated:
            await _safe_edit(bot, chat_id, message_id, accumulated)

        # Required: bare yield to keep this an async generator.
        # Telegram delivers by side effect; the protocol's signature is
        # AsyncIterator[bytes], so we have to yield SOMETHING — but we
        # never actually reach the yield because of the return above.
        return
        yield  # noqa: unreachable, makes this an async generator


async def _safe_edit(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    """Edit the placeholder. Swallow benign Telegram errors."""
    if len(text) > _MAX_MESSAGE_LEN:
        text = text[: _MAX_MESSAGE_LEN - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX

    try:
        await bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramRetryAfter as exc:
        # Flood-control. Honor the cooldown — sleeping here pauses the
        # debounce timer, which is exactly what we want.
        logger.warning("TELEGRAM_FLOOD_CONTROL retry_after=%s", exc.retry_after)
        await asyncio.sleep(exc.retry_after)
    except TelegramBadRequest as exc:
        # "message is not modified" — fine, the accumulated text didn't
        # change since last edit (e.g. only whitespace deltas). Anything
        # else, log but don't re-raise: partial delivery beats a thrown
        # stream.
        if "message is not modified" in str(exc):
            return
        logger.exception("TELEGRAM_EDIT_FAILED chat_id=%s message_id=%s",
                         chat_id, message_id)
```

Drop the existing top-of-file TODOs once their concerns are addressed.

### 2. `backend/app/integrations/telegram/bot.py` — placeholder + `deliver` call

Replace the Step-2 plain text handler. New flow:

```python
@router.message(F.text)
async def handle_text(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_maker() as session:
        user_id = await get_user_id_for_external(
            provider="telegram",
            external_user_id=str(message.from_user.id),
            session=session,
        )
        if user_id is None:
            await message.answer(_NOT_BOUND_MESSAGE)
            return

        conv = await get_or_create_telegram_conversation(user_id, session)

        # 1. Send the placeholder up front.
        placeholder = await message.answer("⏳")

        # 2. Persist the user message before starting the stream so
        #    a mid-stream crash doesn't lose it.
        await append_user_message(conv.id, message.text or "", session)

        # 3. Build the provider stream (same call path Step 2 used,
        #    but DON'T consume it — hand it to the channel).
        history = await load_history(conv.id, session)
        provider = resolve_llm(...)  # same as Step 2
        provider_stream = provider.stream(history, ...)

        # 4. Build the ChannelMessage and drive deliver().
        channel_msg: ChannelMessage = {
            "user_id": user_id,
            "conversation_id": conv.id,
            "text": message.text or "",
            "surface": "telegram",
            "model_id": conv.model_id,
            "metadata": {
                "bot": message.bot,
                "chat_id": message.chat.id,
                "message_id": placeholder.message_id,
            },
        }

        channel = resolve_channel("telegram")
        # We need the final accumulated text for persistence. Easiest:
        # tee the stream so deliver() consumes one side and we keep the
        # other for the DB write. Or rework deliver() to expose the
        # final string. Simplest path: wrap the provider stream in a
        # small async generator that records each delta into a local
        # list while yielding events through. Then deliver() drains it,
        # and we join the list afterward for persistence.
        recorded: list[str] = []
        async def _record_and_yield():
            async for ev in provider_stream:
                if ev.get("type") == "delta":
                    recorded.append(ev.get("content", ""))
                yield ev

        async for _ in channel.deliver(_record_and_yield(), channel_msg):
            pass

        final = "".join(recorded) or "[empty response]"
        await append_assistant_message(conv.id, final, session)
```

Two important details:

- **Persistence is your responsibility, not the channel's.** `deliver()`
  handles VISUAL delivery (edit the placeholder). The DB write happens
  in the handler. Don't move it into `deliver()` — that couples the
  channel adapter to the persistence layer.
- **The tee pattern (`_record_and_yield`)** keeps the channel
  abstraction clean. The alternative — having `deliver()` return the
  final string — would mean either changing the protocol signature
  (breaks `SSEChannel`) or shoehorning a return path that's awkward for
  an async generator. The tee is uglier but local.

### 3. Optional cleanup: typing indicator refresh

Telegram's typing indicator clears ~5 seconds after the last
`sendChatAction`. With a long stream (debounce delays + LLM latency),
the indicator will flicker off then back on with each edit. If that
bothers you, add a small background task that refreshes
`sendChatAction` every 2.5s for the duration of the stream and cancels
in the handler's `finally`. Skip if it looks fine in practice.

## Footguns

- **Don't iterate the provider stream twice.** Async generators can
  only be consumed once. The tee pattern is mandatory if you want both
  the live edits and the final persisted string.
- **`message is not modified`**: Telegram throws this if you call
  `edit_message_text` with identical text. Happens when the accumulator
  hasn't grown since the last edit (rare but possible with whitespace-
  only deltas). The `_safe_edit` swallow path handles it.
- **Empty stream**: if the provider yields no deltas (catalog miss,
  model returned nothing), `accumulated` is empty and the final flush
  is skipped. The placeholder will sit at `⏳` forever. Detect empty
  after the stream and edit to `[no response]` or similar before
  exiting deliver — OR do it in the handler after the `async for`
  loop. Pick one place, document it.
- **The `return; yield` pattern**: this is intentional and Python
  needs it to make the function an async generator (the type signature
  is `AsyncIterator[bytes]` per the Channel protocol). Linters may
  complain about unreachable code. `# noqa` it.
- **TelegramRetryAfter sleep**: when this fires, the entire `deliver()`
  call pauses. That's the correct behavior — the LLM stream keeps
  accumulating in memory, and we resume editing once the cooldown
  ends. Just be aware that long retry-after values (60+ seconds) will
  feel very stuck to the user. Telegram normally only asks for 1–5s
  unless you're being abusive.
- **Don't try to chunk into multiple Telegram messages on overflow.**
  The placeholder is a single `message_id`. `editMessageText` can only
  target that one ID. Splitting requires sending NEW messages, which
  defeats the "edit one message in place" UX. Defer to a future step.

## Out of scope

- Multi-message splitting on responses > 4096 chars.
- `/stop` cancellation of the in-flight task.
- Tool-call status icons rendered between deltas.
- Reasoning blocks ("thinking…") rendered separately from the main
  response.
- Forum topic routing.
- Auto-title generation post-turn.
- Webhook mode (still polling).

## How to test it

1. Steps 1 and 2 shipped.
2. Send "tell me a 10 sentence story about a dragon" to the bot.
3. Expect `⏳` within half a second.
4. Within 1–3 seconds, that message starts containing partial text.
5. Watch the message grow over the next few seconds. Edits feel
   smooth (not one-character-at-a-time, not 10-second-pauses).
6. Final response is complete, no truncation suffix.
7. Send "write me a 5000 word essay". Expect the message to grow,
   end with `…` once it hits 4096 chars, no error in the bot.
8. Web app shows the same conversation with both messages persisted
   (full assistant message, not just the first 4096 chars).
9. Send 5 quick messages in a row. The placeholder/edit machinery
   for each should run independently — no retry-after spam.
