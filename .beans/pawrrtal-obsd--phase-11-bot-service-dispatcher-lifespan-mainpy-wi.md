---
# pawrrtal-obsd
title: Phase 11 — Bot service + dispatcher + lifespan + main.py wiring
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:13Z
updated_at: 2026-05-14T19:52:13Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-0v4v
---

## Why

This is the **last bean** — the file that brings everything together. The
aiogram dispatcher routes inbound updates to your handlers; the LLM turn
runner glues handlers → provider → channel → persistence; the lifespan starts
and stops it all alongside the FastAPI app.

Most of the complexity is in `_run_llm_turn` (the turn coordinator) and the
lifespan's polling/webhook split. Everything else is plumbing.

## What to build

Two files:

1. `backend/app/integrations/telegram/bot.py` — the big one.
2. Re-add the integration in `backend/main.py`.

### File 1: `bot.py`

#### Module-level state

```
# Process-local map of chat_id -> running stream Task.
# CRITICAL: this is single-process. A /stop on uvicorn worker A cannot cancel
# a stream on worker B. If you ever scale to multiple workers, this must
# become Redis pub/sub. For now: document the limitation, single-worker only.
_running_tasks: dict[int, asyncio.Task[None]] = {}
```

#### `TelegramService` dataclass

```
@dataclass
class TelegramService:
    bot: Bot
    dispatcher: Dispatcher
    polling_task: asyncio.Task[None] | None = None

    async def feed_webhook_update(self, update: Update) -> None:
        # Used by the FastAPI webhook route. Polling never calls this.
        await self.dispatcher.feed_update(self.bot, update)
```

#### `_sender_from_message(message: Message) -> TelegramSender`

```
user <- message.from_user
if user is None:
    # Anonymous channel posts — we don't handle these
    raise RuntimeError("Telegram message has no from_user; refusing to dispatch.")
return TelegramSender(
    user_id=user.id,
    chat_id=message.chat.id,
    username=user.username,
    full_name=user.full_name,
    thread_id=message.message_thread_id,   # None for non-forum chats
)
```

#### `_extract_start_payload(text: str) -> str | None`

aiogram exposes the deep-link argument via `CommandObject.args`, but reading
from `message.text` keeps this handler robust to users manually typing
`/start ABC123`.

```
_START_COMMAND_PARTS_WITH_PAYLOAD = 2

def _extract_start_payload(text: str) -> str | None:
    parts <- text.strip().split(maxsplit=1)
    if len(parts) < 2: return None
    return parts[1].strip() or None
```

#### `_resolve_provider_with_auto_clear(context) -> tuple[AILLM, str | None]`

The **auto-clear safety net** for unknown stored model IDs. If a user
previously did `/model some-broken-id`, `parse_model_id` accepted it but the
catalog doesn't know it. Without this helper, every subsequent turn fails
with the same error forever.

```
try:
    require_known(context.model_id)            # raises UnknownModelId on catalog miss
    provider <- resolve_llm(context.model_id, user_id=context.nexus_user_id)
except (InvalidModelId, UnknownModelId) as exc:
    fallback_id <- default_model().id
    warning     <- f"Model <code>{context.model_id}</code> isn't usable: {exc}. " \
                   f"Switching you back to the default ({fallback_id})."
    async with async_session_maker() as session:
        await update_conversation_model(
            conversation_id=context.conversation_id, model_id=None, session=session,
        )                                       # NULL = next turn reads catalog default
    logger.info("TELEGRAM_MODEL_AUTO_CLEAR conversation_id=%s bad_model=%s",
                context.conversation_id, context.model_id)
    provider <- resolve_llm(fallback_id, user_id=context.nexus_user_id)
    return provider, warning
return provider, None
```

The returned `warning` is a user-facing string the caller posts before the
LLM reply, so the user knows their model got reset.

#### `_run_llm_turn(*, message, context) -> None` — the LLM turn coordinator

```
user_text <- message.text or ""
if message.bot is None:
    raise RuntimeError("Telegram message has no bot; refusing to stream.")
thinking_msg <- await message.answer("⏳")        # the placeholder we'll edit

# --- Workspace + tools (lazy imports — bot.py shouldn't always pay them) ---
from app.channels.telegram     import make_telegram_sender
from app.core.agent_tools      import build_agent_tools
from app.core.tools.agents_md  import assemble_workspace_prompt
from app.crud.workspace        import get_default_workspace

async with async_session_maker() as ws_session:
    workspace <- await get_default_workspace(context.nexus_user_id, ws_session)

tg_sender   <- make_telegram_sender(message.bot, message.chat.id,
                                    message_thread_id=context.thread_id)
agent_tools <- build_agent_tools(workspace_root=Path(workspace.path),
                                 user_id=context.nexus_user_id,
                                 send_fn=tg_sender) if workspace else []
workspace_system_prompt <- assemble_workspace_prompt(Path(workspace.path)) if workspace else None

# --- Provider with auto-clear ---
provider, warning <- await _resolve_provider_with_auto_clear(context)
if warning is not None:
    await message.answer(warning)

# --- Cancel any in-flight stream for this chat before starting ours ---
async def _do_stream():
    await stream_persisted_turn(
        message=message, context=context, user_text=user_text,
        placeholder_message_id=thinking_msg.message_id,
        provider=provider, agent_tools=agent_tools,
        workspace_system_prompt=workspace_system_prompt,
    )

chat_id  <- message.chat.id
old_task <- _running_tasks.pop(chat_id, None)
if old_task is not None and not old_task.done():
    old_task.cancel()                           # /stop equivalent — but the new msg wins

task <- asyncio.create_task(_do_stream())
_running_tasks[chat_id] = task
try:
    await task
except asyncio.CancelledError:
    logger.info("TELEGRAM_STREAM_CANCELLED chat_id=%s", chat_id)
finally:
    _running_tasks.pop(chat_id, None)            # clean up regardless

# --- Post-turn: auto-title (fire-and-forget) ---
try:
    await _maybe_set_auto_title(
        bot=message.bot, conversation_id=context.conversation_id,
        user_text=user_text, chat_id=message.chat.id, thread_id=context.thread_id,
    )
except Exception:
    logger.warning("TELEGRAM_AUTO_TITLE_FAILED", exc_info=True)
```

**Why cancel-then-create instead of "ignore if already running"**: a second
message from the same chat is almost always a course-correction. The user
expects their new message to be the live one, not silently dropped. New
message wins.

**Why pop in `finally`**: even on `CancelledError` we clean up so the dict
doesn't accumulate dead tasks.

#### `build_telegram_service() -> TelegramService` — register dispatcher routes

```
# Lazy import — aiogram only loads when the channel is actually configured
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart

if not settings.telegram_bot_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN must be set to start the Telegram service.")

bot        <- Bot(token=settings.telegram_bot_token,
                  default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dispatcher <- Dispatcher()

# Route /start (with and without deep-link payload)
@dispatcher.message(CommandStart(deep_link=True))
@dispatcher.message(CommandStart())
async def _on_start(message):
    sender  <- _sender_from_message(message)
    payload <- _extract_start_payload(message.text or "")
    async with async_session_maker() as session:
        reply <- await handle_start_command(sender=sender, payload=payload, session=session)
    await message.answer(reply)

# /stop — cancel + reply
@dispatcher.message(Command("stop"))
async def _on_stop(message):
    chat_id     <- message.chat.id
    task        <- _running_tasks.pop(chat_id, None)
    was_running <- task is not None and not task.done()
    if was_running:
        task.cancel()
    reply <- handle_stop_command(was_running=was_running)    # sync — no await
    await message.answer(reply)

# /new — fresh conversation, same topic
@dispatcher.message(Command("new"))
async def _on_new(message):
    sender <- _sender_from_message(message)
    async with async_session_maker() as session:
        reply <- await handle_new_command(sender=sender, session=session)
    await message.answer(reply)

# /model <id> — parse + persist
@dispatcher.message(Command("model"))
async def _on_model(message):
    text   <- message.text or ""
    parts  <- text.strip().split(maxsplit=1)
    model_arg <- parts[1].strip() if len(parts) > 1 else ""
    sender <- _sender_from_message(message)
    async with async_session_maker() as session:
        reply <- await handle_model_command(sender=sender, model_arg=model_arg, session=session)
    await message.answer(reply)

# Default — any text message
@dispatcher.message()
async def _on_message(message):
    if not message.text:                       # ignore photos, stickers, voice, etc.
        return
    sender <- _sender_from_message(message)
    async with async_session_maker() as session:
        result <- await handle_plain_message(sender=sender, text=message.text, session=session)
    if isinstance(result, str):
        # Terminal reply (not bound, code redemption confirmation, etc.)
        await message.answer(result)
        return
    # TurnContext — route to LLM
    await _run_llm_turn(message=message, context=result)

return TelegramService(bot=bot, dispatcher=dispatcher)
```

**Order of `@dispatcher.message` decorators matters** — aiogram matches the
first one whose filter accepts the update. `CommandStart` before generic
`@dispatcher.message()` is mandatory.

The double decorator on `_on_start` (deep_link=True + plain) is the
recommended aiogram pattern for "accept /start with OR without a payload".

#### `telegram_lifespan() -> AsyncContextManager[TelegramService | None]`

```
@asynccontextmanager
async def telegram_lifespan():
    if settings.demo_mode:
        logger.info("TELEGRAM_DISABLED reason=demo_mode")
        yield None
        return
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_DISABLED reason=no_token")
        yield None
        return

    service <- build_telegram_service()

    if settings.telegram_mode == "polling":
        # Drop any leftover webhook — telegram silently swallows getUpdates
        # when a webhook is set. This is the #1 local-dev footgun.
        await service.bot.delete_webhook(drop_pending_updates=True)
        logger.info("TELEGRAM_BOOT mode=polling")
        service.polling_task <- asyncio.create_task(
            service.dispatcher.start_polling(service.bot, handle_signals=False),
            name="telegram-polling",
        )
    else:
        url <- settings.telegram_webhook_url
        if not url:
            raise RuntimeError("TELEGRAM_MODE=webhook requires TELEGRAM_WEBHOOK_URL to be set.")
        secret <- settings.telegram_webhook_secret or None
        await service.bot.set_webhook(url=url, secret_token=secret, drop_pending_updates=True)
        logger.info("TELEGRAM_BOOT mode=webhook url=%s", url)

    try:
        yield service
    finally:
        if service.polling_task is not None:
            service.polling_task.cancel()
            # Either CancelledError or a teardown error — both fine, we're shutting down
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await service.polling_task
        try:
            await service.bot.session.close()
        except Exception:
            logger.warning("TELEGRAM_SHUTDOWN session_close_failed", exc_info=True)
```

**Three reasons it might `yield None`**:
1. Demo mode is on (bot is intentionally locked off — see
   `docs/deployment/demo-mode.md`).
2. No bot token configured (clean disable, no error).
3. Future hooks like `telegram_disabled=True` env flag (extend here).

**`handle_signals=False`**: aiogram's polling loop by default installs
`SIGINT/SIGTERM` handlers, which fight with FastAPI/uvicorn's lifecycle.
Disable it — the lifespan owns shutdown.

**`drop_pending_updates=True`** on both modes: clear any backlog from before
your bot started. Don't process week-old messages.

### File 2: `backend/main.py` — re-add the wiring

Top of file (after other imports):

```
from app.api.channels import get_channels_router
from app.integrations.telegram import telegram_lifespan
```

Inside the `lifespan` function (the deletion left placeholder comments):

```
async with telegram_lifespan() as telegram_service:
    app.state.telegram_service = telegram_service     # webhook route reads this
    try:
        yield
    finally:
        shutdown_tracing()
```

In `create_app`, add the router registration:

```
fastapi_app.include_router(get_channels_router())
```

### `__init__.py` re-exports

`backend/app/integrations/telegram/__init__.py`:

```
from app.integrations.telegram.bot import (
    TelegramService,
    build_telegram_service,
    telegram_lifespan,
)
__all__ = ["TelegramService", "build_telegram_service", "telegram_lifespan"]
```

## Edge cases — every one a story

- **Demo mode**: must check BEFORE the token check. A demo deploy might have
  a real token in its env (operator forgot to clear it); demo mode wins.
- **Polling without delete_webhook**: silent failure. `getUpdates` returns
  nothing because Telegram thinks you're on webhook. **Always call
  `delete_webhook(drop_pending_updates=True)` before polling.**
- **Webhook secret None vs empty string**: `secret_token=None` on aiogram
  omits the param. `secret_token=""` sends an empty string. Use `... or None`.
- **`message.bot` may be None** in some edge aiogram versions — guard before
  using. The handlers don't see this; only `_run_llm_turn` does.
- **`message.from_user` can be None** for anonymous channel posts. We reject
  these at `_sender_from_message`. The dispatcher catches the RuntimeError
  and aiogram logs it; the bot stays up.
- **`task.cancel()` doesn't synchronously cancel**: it requests cancellation
  at the next `await`. The cancelled task may finish one more iteration of
  the stream loop before exiting. That's fine — the stream wrapper's
  `finally` block runs either way.
- **Multiple lifespan errors during shutdown**: any error in `polling_task`
  cleanup or `bot.session.close()` is logged-and-swallowed. The lifespan is
  already tearing down — propagating an exception here would block uvicorn's
  shutdown.

## Tests that should pass after this

Everything left:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_telegram_channel.py \
  tests/test_channels.py \
  tests/test_channels_api.py \
  tests/test_send_message_tool.py
```

`TestResolveProviderWithAutoClear` in `test_telegram_channel.py` exercises
`_resolve_provider_with_auto_clear` — that test cluster goes green here.

End-to-end smoke (manual):

```bash
# 1. Set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME in backend/.env
# 2. Run: just dev
# 3. In the web UI: Settings → Channels → Connect Telegram → copy code
# 4. In Telegram: send the code to your bot
# 5. Send "hello" — you should see the "⏳" placeholder, then the streamed reply
# 6. Send "/stop" mid-stream — placeholder freezes, "⏹ Stopped." replies
# 7. Send "/model anthropic/claude-sonnet-4-6" — model switched reply
# 8. Send "what's 2+2" — streams from the new model
```

## You did it

The whole channel is end-to-end functional after this bean. The next layer of
follow-ups (multi-worker /stop via Redis, splitting >4096-char replies,
proactive catalog validation at /model time, real-time web push instead of
polling) are scope-bound to separate beans, not blockers for this rebuild.
