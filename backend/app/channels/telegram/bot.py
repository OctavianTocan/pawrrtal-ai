"""aiogram-backed Telegram bot service.

Thin glue between aiogram's ``Bot`` + ``Dispatcher`` and the framework-free
handlers in :mod:`app.channels.telegram.handlers`. Two boot modes:

- **polling** (default; works on a laptop with no inbound connectivity):
  the FastAPI lifespan launches a background task that calls
  ``Dispatcher.start_polling``. No tunnel, no ngrok, no webhook URL.

- **webhook** (production): the lifespan registers the webhook with
  Telegram on startup and the FastAPI app exposes a route that aiogram
  feeds via ``feed_webhook_update``. Set
  ``TELEGRAM_MODE=webhook`` + ``TELEGRAM_WEBHOOK_URL`` to enable.

Both paths share the same handler functions, so anything we test for
polling automatically covers webhook.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.agents.tool_surface import build_agent_tools
from app.channels.base import ChannelMessage
from app.channels.telegram.bot_runtime import (
    COMMAND_REFRESH_COOLDOWN_SECONDS,
    ChatMessageQueueDispatcher,
    QueuedTurn,
    TelegramPollingLock,
    defer_command_refresh,
    handle_compact_command,
    handle_lcm_command,
    handle_status_command,
    normalize_reasoning_and_notify,
    prepare_telegram_media_context,
    resolve_provider_with_auto_clear,
    safe_edit_html,
    should_refresh_commands,
)
from app.channels.telegram.handlers import (
    TelegramSender,
    TelegramTurnContext,
    collect_attachments,
    handle_new_command,
    handle_plain_message,
    handle_start_command,
    handle_stop_command,
    handle_verbose_command,
    handle_whoami_command,
)
from app.channels.turn_orchestrator import ChatTurnInput, run_turn
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import async_session_maker
from app.plugins.adapters.turn_context import build_turn_context_providers
from app.providers.session_preparer import prepare_provider_session

from .channel import SURFACE_TELEGRAM, make_telegram_sender, render_initial

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.types import CallbackQuery, Message, ReplyParameters, Update

    from app.channels.telegram._attachments import TelegramVoiceNote

logger = logging.getLogger(__name__)

_TELEGRAM_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Connect your Pawrrtal account"),
    ("new", "Start a new conversation"),
    ("model", "Pick or set the model (no arg = picker)"),
    ("thinking", "Pick the reasoning level for the current model"),
    ("config", "Toggle workspace features"),
    ("verbose", "Set detail level: 0 quiet, 1 tools, 2 thinking"),
    ("stop", "Stop the active run"),
    ("status", "Show gateway + conversation status"),
    ("whoami", "Show your Telegram ID and Pawrrtal binding"),
    ("lcm", "Show LCM (long-context memory) status for this conversation"),
    ("compact", "Force an LCM leaf-compaction pass now"),
)

# Captured at module import so /status can report this worker's uptime
# without reading the wall clock at boot. Process-local — multi-worker
# deployments report only the worker that handled the command.
_BOT_START_MONOTONIC: float = time.monotonic()


def get_bot_uptime_seconds() -> float:
    """Return seconds since this worker's process started."""
    return time.monotonic() - _BOT_START_MONOTONIC


def is_chat_run_active(chat_id: int) -> bool:
    """Return whether an agent run is in flight for ``chat_id`` on this worker.

    When the FIFO dispatcher is enabled (``settings.telegram_chat_queue_enabled``),
    delegates to :meth:`ChatMessageQueueDispatcher.is_running`; otherwise
    reads the direct-execution task table.
    """
    if settings.telegram_chat_queue_enabled:
        return _get_chat_queue_dispatcher().is_running(chat_id)
    task = _running_tasks.get(chat_id)
    return task is not None and not task.done()


# Active streaming tasks keyed by Telegram chat_id.  When a new message
# arrives we cancel any existing task for that chat (preventing two parallel
# streams into the same placeholder message), then store the new one so
# a subsequent /stop can cancel it.
#
# IMPORTANT — this dict is PROCESS-LOCAL.  A /stop arriving on worker A
# cannot cancel a task running on worker B.  This is correct for the current
# single-worker deployment; promote to a shared store (e.g. Redis pub/sub)
# before running multiple uvicorn workers.
#
# When ``settings.telegram_chat_queue_enabled`` is true, the FIFO dispatcher
# owns this state instead.
_running_tasks: dict[int, asyncio.Task[None]] = {}


# Singleton per-chat FIFO turn queue, built lazily so processes that never
# enable it pay no overhead.
_CHAT_QUEUE_DISPATCHER: ChatMessageQueueDispatcher | None = None


def _get_chat_queue_dispatcher() -> ChatMessageQueueDispatcher:
    """Return the process-wide chat-queue dispatcher, building on first use."""
    global _CHAT_QUEUE_DISPATCHER  # noqa: PLW0603 — singleton accessor pattern
    if _CHAT_QUEUE_DISPATCHER is None:
        _CHAT_QUEUE_DISPATCHER = ChatMessageQueueDispatcher(consumer=_chat_queue_consumer)
    return _CHAT_QUEUE_DISPATCHER


async def _chat_queue_consumer(turn: QueuedTurn) -> None:
    """Default consumer — runs the turn payload that ``_run_llm_turn`` enqueued.

    The payload is the bound coroutine factory ``_run_llm_turn`` would
    have invoked synchronously; the consumer awaits it under the
    dispatcher's per-chat serialised worker so messages arriving
    mid-turn queue up instead of clobbering the in-flight reply.
    """
    coro_factory = turn.payload
    if not callable(coro_factory):
        logger.warning(
            "TELEGRAM_CHAT_QUEUE_BAD_PAYLOAD chat_id=%s type=%s",
            turn.chat_id,
            type(coro_factory).__name__,
        )
        return
    await coro_factory()


async def _execute_turn_body(
    *,
    message: Message,
    turn_input: ChatTurnInput,
    user_text: str,
    context: TelegramTurnContext,
) -> None:
    """Run the typing + stream + auto-title block under the FIFO dispatcher.

    Extracted from :func:`_run_llm_turn` so the dispatcher's consumer
    has a clean callable to await. The direct path still inlines this
    logic with its own ``_running_tasks`` bookkeeping.
    """
    chat_id = message.chat.id
    bot = message.bot
    assert bot is not None
    typing_task: asyncio.Task[None] | None = None
    if settings.telegram_typing_indicator_enabled:
        typing_task = asyncio.create_task(
            _maintain_typing_indicator(bot, chat_id, context.thread_id),
            name=f"telegram-typing-{chat_id}",
        )
    try:
        async for _ in run_turn(turn_input):
            pass
    except asyncio.CancelledError:
        logger.info("TELEGRAM_STREAM_CANCELLED chat_id=%s", chat_id)
        raise
    finally:
        if typing_task is not None:
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await typing_task

    try:
        await _maybe_set_auto_title(
            bot=bot,
            conversation_id=context.conversation_id,
            user_text=user_text,
            chat_id=chat_id,
            thread_id=context.thread_id,
        )
    except Exception:
        logger.warning("TELEGRAM_AUTO_TITLE_FAILED", exc_info=True)


async def shutdown_chat_queue_dispatcher() -> None:
    """Cancel every per-chat worker on bot shutdown.

    Called from the bot's lifespan teardown so a clean ``SIGTERM``
    doesn't leak dispatcher task references. No-op when the
    dispatcher was never constructed.
    """
    if _CHAT_QUEUE_DISPATCHER is not None:
        await _CHAT_QUEUE_DISPATCHER.shutdown()


async def _send_one_typing_action(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
) -> None:
    """Best-effort single ``sendChatAction`` — log and swallow on failure."""
    try:
        if thread_id is not None:
            await bot.send_chat_action(
                chat_id=chat_id,
                action="typing",
                message_thread_id=thread_id,
            )
        else:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        logger.debug(
            "TELEGRAM_TYPING_FAILED chat_id=%s thread_id=%s",
            chat_id,
            thread_id,
            exc_info=True,
        )


async def _maintain_typing_indicator(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
) -> None:
    """Refresh the Telegram typing indicator on a timer until cancelled.

    Telegram clears the "typing…" hint roughly 5 seconds after the
    last ``sendChatAction`` call.  Refreshing every
    ``settings.telegram_typing_refresh_seconds`` (default 2.5s) keeps
    the indicator visible for the whole agent run so the user always
    sees that the bot is working — matches CCT's persistent-typing
    behaviour.

    Per-iteration errors are swallowed inside ``_send_one_typing_action``
    so a single failed ``sendChatAction`` never breaks the agent run.
    The whole task is cancelled by the caller's finally block.
    """
    refresh = settings.telegram_typing_refresh_seconds
    try:
        while True:
            await _send_one_typing_action(bot, chat_id, thread_id)
            await asyncio.sleep(refresh)
    except asyncio.CancelledError:
        return


def _reply_parameters(message_id: int) -> ReplyParameters | None:
    """Build aiogram reply parameters without importing aiogram at module load."""
    if message_id <= 0:
        return None
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)


# TODO: This is pretty nonsensical. We have a custom entire chat impkementation that just duplicates the logic here.
async def _run_llm_turn(  # noqa: C901, PLR0915
    *,
    message: Message,
    context: TelegramTurnContext,
    images: list[dict[str, str]] | None = None,
    voice_notes: list[TelegramVoiceNote] | None = None,
    text_annotations: list[str] | None = None,
) -> None:
    """Drive the LLM streaming pipeline for one Telegram turn.

    Extracted from ``_on_message`` to keep that dispatcher closure narrow
    enough to satisfy the project's complexity cap.  Sends a placeholder
    reply, resolves the provider (with the auto-clear safety net),
    builds the channel message, streams the response, and finally fires
    the auto-title pass.

    Args:
        message: The inbound aiogram ``Message`` (used for ``answer``,
            ``chat.id``, ``bot``, and ``message_thread_id``).
        context: Resolved turn context from ``handle_plain_message``.
        images: Image inputs collected via :func:`collect_attachments`
            and interpreted before the main provider runs.
        voice_notes: Downloaded Telegram voice-note payloads. Transcribed
            before the main provider runs.
        text_annotations: ``"User sent X."`` lines appended to the
            user message body so the agent has metadata for voice /
            document attachments we could not fully extract.
    """
    base_text = (message.text or message.caption or "").strip()
    if message.bot is None:
        raise RuntimeError("Telegram message has no bot; refusing to stream.")
    thinking_msg = await message.answer(
        render_initial(),
    )

    # Keep startup imports lazy and keep fan-out count within limit
    from app.workspace.crud import get_default_workspace  # noqa: PLC0415

    async with async_session_maker() as ws_session:
        workspace = await get_default_workspace(context.pawrrtal_user_id, ws_session)
    workspace_root = Path(workspace.path) if workspace is not None else None

    prepared_annotations = await prepare_telegram_media_context(
        images=images,
        voice_notes=voice_notes or [],
        text_annotations=text_annotations or [],
        workspace_root=workspace_root,
        conversation_id=context.conversation_id,
        user_id=context.pawrrtal_user_id,
        user_prompt=base_text,
    )
    annotation_block = "\n".join(prepared_annotations).strip()
    if base_text and annotation_block:
        user_text = f"{base_text}\n\n{annotation_block}"
    else:
        # Either: text-only message, attachment-only message, or both
        # — string concat falls through to whichever is non-empty.
        user_text = base_text or annotation_block or "[attachment-only message]"

    tg_sender = make_telegram_sender(
        message.bot,
        message.chat.id,
        message_thread_id=context.thread_id,
        reply_to_message_id=None,
    )
    agent_tools = (
        build_agent_tools(
            workspace_root=Path(workspace.path),
            user_id=context.pawrrtal_user_id,
            workspace_id=workspace.id,
            send_fn=tg_sender,
            surface="telegram",
            conversation_id=context.conversation_id,
            model_id=context.model_id,
        )
        if workspace is not None
        else []
    )
    turn_context_providers = (
        build_turn_context_providers(workspace_root=workspace_root)
        if workspace_root is not None
        else []
    )

    provider, warning = await resolve_provider_with_auto_clear(
        context,
        workspace_root=workspace_root,
    )
    if warning is not None:
        await message.answer(warning, reply_parameters=_reply_parameters(message.message_id))

    channel_message: ChannelMessage = {
        "user_id": context.pawrrtal_user_id,
        "conversation_id": context.conversation_id,
        "text": user_text,
        "surface": SURFACE_TELEGRAM,
        "model_id": context.model_id,
        "metadata": {
            "bot": message.bot,
            "chat_id": message.chat.id,
            "message_id": thinking_msg.message_id,
            "message_thread_id": context.thread_id,
        },
    }

    # Backstop: re-validate the stored reasoning_effort against the
    # current model. Telegram's /thinking picker writes the column,
    # but model changes (via /model, the picker, or any future
    # surface) can leave the stored value out of sync with what the
    # model honours. The shared resolver in
    # `app.providers.reasoning` adapts or clears the override;
    # the helper sends a Telegram notice whenever a change happens
    # so the new behaviour isn't silent. Returns ``None`` for the
    # "let the provider pick its default" case.
    effective_effort = await normalize_reasoning_and_notify(
        message=message,
        conversation_id=context.conversation_id,
        model_id=context.model_id,
    )
    provider_session = await prepare_provider_session(
        provider,
        conversation_id=context.conversation_id,
        workspace_root=workspace_root,
        model_id=context.model_id,
        tools=agent_tools,
        reasoning_effort=effective_effort,
        question=user_text,
    )

    has_active_recall = False

    async def _draft_updater(html: str) -> None:
        nonlocal has_active_recall
        has_active_recall = True
        if message.bot:
            await safe_edit_html(message.bot, message.chat.id, thinking_msg.message_id, html)

    async def _on_turn_context_finished() -> None:
        if has_active_recall:
            nonlocal thinking_msg
            # Spawn a new placeholder so the active recall message stays in the chat history
            thinking_msg = await message.answer(
                render_initial(),
            )
            channel_message["metadata"]["message_id"] = thinking_msg.message_id

    from app.channels.registry import resolve_channel  # noqa: PLC0415

    turn_input = ChatTurnInput(
        conversation_id=context.conversation_id,
        user_id=context.pawrrtal_user_id,
        question=user_text,
        provider=provider,
        channel=resolve_channel(SURFACE_TELEGRAM),
        channel_message=channel_message,
        workspace_root=workspace_root,
        tools=agent_tools,
        images=None,
        # Helper to let context providers stream progress into the placeholder message.
        draft_updater=_draft_updater,
        on_turn_context_finished=_on_turn_context_finished,
        log_tag="TELEGRAM",
        log_extras={"chat_id": message.chat.id},
        verbose_level=(
            context.verbose_level
            if context.verbose_level is not None
            else settings.telegram_verbose_default
        ),
        turn_context_providers=turn_context_providers,
        reasoning_effort=effective_effort,
        provider_session=provider_session,
    )

    async def _do_stream() -> None:
        async for _ in run_turn(turn_input):
            pass

    chat_id = message.chat.id

    if settings.telegram_chat_queue_enabled:
        # The per-chat worker drains queued turns serially instead of
        # clobbering the in-flight turn.
        async def _enqueued_body() -> None:
            await _execute_turn_body(
                message=message,
                turn_input=turn_input,
                user_text=user_text,
                context=context,
            )

        await _get_chat_queue_dispatcher().enqueue(
            QueuedTurn(
                chat_id=chat_id,
                payload=_enqueued_body,
                enqueued_at_monotonic=asyncio.get_event_loop().time(),
            )
        )
        return

    # Legacy "cancel previous task" path. Kept until the FIFO mode
    # has baked in a production deployment, then this branch can be
    # deleted and the helper inlined.
    old_task = _running_tasks.pop(chat_id, None)
    if old_task is not None and not old_task.done():
        old_task.cancel()

    typing_task: asyncio.Task[None] | None = None
    if settings.telegram_typing_indicator_enabled:
        typing_task = asyncio.create_task(
            _maintain_typing_indicator(message.bot, chat_id, context.thread_id),
            name=f"telegram-typing-{chat_id}",
        )

    task: asyncio.Task[None] = asyncio.create_task(_do_stream())
    _running_tasks[chat_id] = task
    try:
        await task
    except asyncio.CancelledError:
        logger.info("TELEGRAM_STREAM_CANCELLED chat_id=%s", chat_id)
    finally:
        _running_tasks.pop(chat_id, None)
        if typing_task is not None:
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await typing_task

    # Auto-title: derive a title from the first user message and
    # rename the Telegram topic thread to match.  Fires once only
    # (gated by title_set_by IS NULL).  Errors are swallowed so a
    # topic-rename failure never breaks the conversation.
    try:
        await _maybe_set_auto_title(
            bot=message.bot,
            conversation_id=context.conversation_id,
            user_text=user_text,
            chat_id=message.chat.id,
            thread_id=context.thread_id,
        )
    except Exception:
        logger.warning("TELEGRAM_AUTO_TITLE_FAILED", exc_info=True)


@dataclass
class TelegramService:
    """Holds the aiogram primitives so the lifespan can stop them cleanly."""

    bot: Bot
    dispatcher: Dispatcher
    polling_task: asyncio.Task[None] | None = None
    polling_lock: TelegramPollingLock | None = None

    async def feed_webhook_update(self, update: Update) -> None:
        """Hand a single ``Update`` parsed from the webhook body to aiogram.

        Used by the FastAPI webhook route in production. Polling does
        not call this — aiogram's polling loop owns its own dispatch.
        """
        await self.dispatcher.feed_update(self.bot, update)


def build_telegram_service() -> TelegramService:
    """Construct the aiogram primitives and register the dispatcher routes.

    Raises ``RuntimeError`` if Telegram support is not configured. The
    lifespan checks the same gate before calling this so the import
    never blows up a deployment that simply doesn't use the channel.
    """
    # Local import: aiogram is only needed when the channel is wired up,
    # so a deployment without TELEGRAM_BOT_TOKEN never pays the cost.
    from aiogram import Bot, Dispatcher  # noqa: PLC0415
    from aiogram.client.default import DefaultBotProperties  # noqa: PLC0415
    from aiogram.enums import ParseMode  # noqa: PLC0415

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be set to start the Telegram service.")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    _register_telegram_command_handlers(dispatcher)
    _register_telegram_callback_handlers(dispatcher)
    _register_telegram_message_handler(dispatcher)

    return TelegramService(bot=bot, dispatcher=dispatcher)


def _register_telegram_command_handlers(dispatcher: Dispatcher) -> None:
    """Register slash-command handlers on the aiogram dispatcher."""
    from aiogram.filters import Command, CommandStart  # noqa: PLC0415

    @dispatcher.message(CommandStart(deep_link=True))
    @dispatcher.message(CommandStart())
    async def _on_start(message: Message) -> None:
        sender = _sender_from_message(message)
        # aiogram exposes the deep-link argument via `command.args` on
        # the parsed CommandObject, but using `message.text` keeps the
        # handler robust if a user manually types `/start ABC123`.
        payload = _extract_start_payload(message.text or "")
        async with async_session_maker() as session:
            reply = await handle_start_command(sender=sender, payload=payload, session=session)
        await message.answer(reply)

    @dispatcher.message(Command("stop"))
    async def _on_stop(message: Message) -> None:
        chat_id = message.chat.id
        if settings.telegram_chat_queue_enabled:
            was_running = await _get_chat_queue_dispatcher().stop_chat(chat_id)
        else:
            task = _running_tasks.pop(chat_id, None)
            was_running = task is not None and not task.done()
            if was_running:
                task.cancel()  # type: ignore[union-attr]
        # handle_stop_command is a plain sync function — no await.
        reply = handle_stop_command(was_running=was_running)
        await message.answer(reply)

    @dispatcher.message(Command("new"))
    async def _on_new(message: Message) -> None:
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            reply = await handle_new_command(sender=sender, session=session)
        await message.answer(reply)

    @dispatcher.message(Command("model"))
    async def _on_model(message: Message) -> None:
        # ``/model`` with no args opens the picker; ``/model <id>``
        # sets the model directly. Single command for both flows —
        # the old ``/models`` alias is gone.
        text = message.text or ""
        parts = text.strip().split(maxsplit=1)
        model_arg = parts[1].strip() if len(parts) > 1 else ""
        model_picker_runtime = import_module("app.channels.telegram.model_picker_runtime")
        await model_picker_runtime.answer_model_command(message=message, model_arg=model_arg)

    @dispatcher.message(Command("thinking"))
    async def _on_thinking(message: Message) -> None:
        thinking_picker_runtime = import_module("app.channels.telegram.thinking_picker_runtime")
        await thinking_picker_runtime.answer_thinking_command(message=message)

    @dispatcher.message(Command("status"))
    async def _on_status(message: Message) -> None:
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            reply = await handle_status_command(
                sender=sender,
                session=session,
                bot_uptime_seconds=get_bot_uptime_seconds(),
                is_chat_run_active=is_chat_run_active,
            )
        await message.answer(reply)

    @dispatcher.message(Command("verbose"))
    async def _on_verbose(message: Message) -> None:
        text = message.text or ""
        parts = text.strip().split(maxsplit=1)
        level_arg = parts[1].strip() if len(parts) > 1 else ""
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            reply = await handle_verbose_command(
                sender=sender, level_arg=level_arg, session=session
            )
        await message.answer(reply)

    _register_telegram_config_command_handler(dispatcher)
    _register_telegram_identity_command_handlers(dispatcher)
    _register_telegram_lcm_command_handlers(dispatcher)


def _register_telegram_config_command_handler(dispatcher: Dispatcher) -> None:
    """Register the workspace config command."""
    from aiogram.filters import Command  # noqa: PLC0415

    @dispatcher.message(Command("config"))
    async def _on_config(message: Message) -> None:
        config_picker_runtime = import_module("app.channels.telegram.config_picker_runtime")
        await config_picker_runtime.answer_config_command(message=message)


def _register_telegram_identity_command_handlers(dispatcher: Dispatcher) -> None:
    """Register identity/diagnostic commands."""
    from aiogram.filters import Command  # noqa: PLC0415

    @dispatcher.message(Command("whoami"))
    async def _on_whoami(message: Message) -> None:
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            reply = await handle_whoami_command(sender=sender, session=session)
        await message.answer(reply)


def _register_telegram_lcm_command_handlers(dispatcher: Dispatcher) -> None:
    """Register LCM-flavoured commands (``/lcm`` + ``/compact``).

    Split out of :func:`_register_telegram_command_handlers` so that
    function stays under the project's PLR0915 cap and so the LCM
    surface lives in one place when future LCM commands land.
    """
    from aiogram.filters import Command  # noqa: PLC0415

    @dispatcher.message(Command("lcm"))
    async def _on_lcm(message: Message) -> None:
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            reply = await handle_lcm_command(sender=sender, session=session)
        await message.answer(reply)

    @dispatcher.message(Command("compact"))
    async def _on_compact(message: Message) -> None:
        # Force a synchronous LCM leaf-compaction pass. Distinct from
        # the per-turn background trigger — surfaces errors instead of
        # swallowing them so the operator gets a real reply.
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            reply = await handle_compact_command(sender=sender, session=session)
        await message.answer(reply)


def _register_telegram_callback_handlers(dispatcher: Dispatcher) -> None:
    """Register inline-keyboard callback handlers on the aiogram dispatcher."""
    model_picker_runtime = import_module("app.channels.telegram.model_picker_runtime")
    config_picker_runtime = import_module("app.channels.telegram.config_picker_runtime")
    regenerate_runtime = import_module("app.channels.telegram.regenerate_runtime")
    thinking_picker_runtime = import_module("app.channels.telegram.thinking_picker_runtime")

    @dispatcher.callback_query(
        lambda query: (query.data or "").startswith(model_picker_runtime.MODEL_CALLBACK_PREFIX)
    )
    async def _on_model_picker(callback: CallbackQuery) -> None:
        await model_picker_runtime.handle_model_picker_callback(callback=callback)

    @dispatcher.callback_query(
        lambda query: (query.data or "").startswith(
            thinking_picker_runtime.THINKING_CALLBACK_PREFIX
        )
    )
    async def _on_thinking_picker(callback: CallbackQuery) -> None:
        await thinking_picker_runtime.handle_thinking_picker_callback(callback=callback)

    @dispatcher.callback_query(
        lambda query: (query.data or "").startswith(config_picker_runtime.CONFIG_CALLBACK_PREFIX)
    )
    async def _on_config_picker(callback: CallbackQuery) -> None:
        await config_picker_runtime.handle_config_picker_callback(callback=callback)

    @dispatcher.callback_query(
        lambda query: (query.data or "").startswith(regenerate_runtime.REGEN_CALLBACK_PREFIX)
    )
    async def _on_regenerate(callback: CallbackQuery) -> None:
        await regenerate_runtime.handle_regenerate_callback(callback=callback)


def _register_telegram_message_handler(dispatcher: Dispatcher) -> None:
    """Register the plain text chat handler on the aiogram dispatcher."""

    @dispatcher.message()
    async def _on_message(message: Message) -> None:
        # Collect attachments before deciding whether a message is empty;
        # media-only updates are still real user turns.
        attachments = (
            await collect_attachments(message, message.bot) if message.bot is not None else None
        )

        # Build the effective user text: caption + annotations.
        text_source = (message.text or message.caption or "").strip()
        has_attachments = attachments is not None and attachments.has_any
        if not text_source and not has_attachments:
            # Nothing actionable — silently drop (matches previous behavior
            # for empty-text messages).
            return

        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            result = await handle_plain_message(
                sender=sender,
                text=text_source or "[attachment-only message]",
                session=session,
            )

        if isinstance(result, str):
            # Terminal reply — user isn't bound or some other error.
            await message.answer(result)
            return

        await _run_llm_turn(
            message=message,
            context=result,
            images=attachments.images if attachments is not None else None,
            voice_notes=attachments.voice_notes if attachments is not None else None,
            text_annotations=(attachments.text_annotations if attachments is not None else None),
        )


async def refresh_telegram_commands(bot: Bot) -> None:
    """Publish the current slash-command menu to Telegram."""
    from aiogram.types import BotCommand  # noqa: PLC0415

    commands = [
        BotCommand(command=command, description=description)
        for command, description in _TELEGRAM_COMMANDS
    ]
    await bot.set_my_commands(commands)
    logger.info(
        "TELEGRAM_COMMANDS_REFRESHED commands=%s",
        ",".join(command for command, _ in _TELEGRAM_COMMANDS),
    )


async def _refresh_telegram_commands_best_effort(bot: Bot) -> None:
    """Refresh command menu without turning Telegram startup into a hard dependency."""
    token = settings.telegram_bot_token
    if token and not should_refresh_commands(token=token):
        logger.info("TELEGRAM_COMMANDS_REFRESH_SKIPPED reason=cooldown")
        return
    try:
        await refresh_telegram_commands(bot)
        if token:
            defer_command_refresh(token=token, seconds=COMMAND_REFRESH_COOLDOWN_SECONDS)
    except Exception as exc:
        retry_after = float(getattr(exc, "retry_after", 0.0) or 0.0)
        if token and retry_after > 0:
            defer_command_refresh(token=token, seconds=retry_after)
        logger.warning("TELEGRAM_COMMANDS_REFRESH_FAILED", exc_info=True)


def _sender_from_message(message: Message) -> TelegramSender:
    """Project an aiogram ``Message`` onto our framework-free dataclass."""
    user = message.from_user
    if user is None:
        # Telegram only delivers `from_user=None` for anonymous channel
        # posts, which we don't care about here.
        raise RuntimeError("Telegram message has no from_user; refusing to dispatch.")
    return TelegramSender(
        user_id=user.id,
        chat_id=message.chat.id,
        username=user.username,
        full_name=user.full_name,
        # Bot API 9.3+: present when the message lives in a topic thread.
        # None for ordinary DMs without topics enabled.
        thread_id=message.message_thread_id,
    )


_START_COMMAND_PARTS_WITH_PAYLOAD = 2
"""``"/start <code>"`` splits into exactly two parts; below this means no payload."""


def _extract_start_payload(text: str) -> str | None:
    """Return the argument after ``/start`` (Telegram deep-link payload), if any."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < _START_COMMAND_PARTS_WITH_PAYLOAD:
        return None
    return parts[1].strip() or None


# ---------------------------------------------------------------------------
# Auto-title helpers (module-level, not inside build_telegram_service)
# ---------------------------------------------------------------------------


def _generate_title(text: str, max_len: int = 48) -> str:
    """Derive a short title from the first user message.

    Strips leading slash-command prefixes (e.g. leftovers from ``/new``),
    truncates to *max_len* characters, appends an ellipsis when truncated,
    and falls back to ``"Telegram"`` for empty input.
    """
    cleaned = text.strip()
    # Strip a leading /command (shouldn't normally reach here, but belt-and-
    # suspenders: the user might type "/new hello" as their first message).
    if cleaned.startswith("/"):
        # Keep everything after the first word (the command itself).
        cleaned = cleaned.split(None, 1)[1] if " " in cleaned else ""
    cleaned = cleaned.strip()
    if not cleaned:
        return "Telegram"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


async def _maybe_set_auto_title(
    *,
    bot: Bot,
    conversation_id: uuid.UUID,
    user_text: str,
    chat_id: int,
    thread_id: int | None,
) -> None:
    """Generate and persist an auto-title for a conversation's first turn.

    Fires once only — gated by ``title_set_by IS NULL``.  On success sets
    ``title_set_by = 'auto'`` so the gate is never tripped again for this
    conversation.  If the conversation lives in a Telegram topic thread,
    also calls ``editForumTopic`` to rename the thread to match, giving
    users a readable label in their Telegram topic list.

    Args:
        bot: Live aiogram ``Bot`` instance.
        conversation_id: UUID of the conversation to maybe-title.
        user_text: The user's first message — used to derive the title.
        chat_id: Telegram chat ID (needed for ``editForumTopic``).
        thread_id: Telegram topic thread ID, or ``None`` for plain DMs.
    """
    async with async_session_maker() as session:
        from app.models import Conversation  # noqa: PLC0415

        conv = await session.get(Conversation, conversation_id)
        if conv is None or conv.title_set_by is not None:
            return  # already titled — nothing to do

        title = _generate_title(user_text)
        conv.title = title
        conv.title_set_by = "auto"
        await session.commit()

    logger.info(
        "TELEGRAM_AUTO_TITLE conversation_id=%s title=%r thread_id=%s",
        conversation_id,
        title,
        thread_id,
    )

    # Rename the Telegram topic thread so the user sees the derived title
    # in their Topics list.  Only possible when the chat has topics enabled
    # and the bot has the necessary admin rights — errors are logged as
    # warnings and swallowed so the feature degrades gracefully.
    if thread_id is not None:
        try:
            await bot.edit_forum_topic(
                chat_id=chat_id,
                message_thread_id=thread_id,
                name=title,
            )
        except Exception as exc:
            logger.warning(
                "TELEGRAM_EDIT_TOPIC_FAILED chat_id=%s thread_id=%s error=%s",
                chat_id,
                thread_id,
                exc,
            )


@asynccontextmanager
async def telegram_lifespan() -> AsyncIterator[TelegramService | None]:
    """Lifespan-friendly context manager that boots + tears down the bot.

    Yields ``None`` when Telegram is intentionally disabled (no bot
    token) so callers can ``async with`` unconditionally without the
    callsite branching on configuration. Yields a live ``TelegramService``
    otherwise — and ensures the polling task or webhook registration is
    properly cleaned up on shutdown.
    """
    if settings.demo_mode:
        logger.info("TELEGRAM_DISABLED reason=demo_mode")
        yield None
        return
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_DISABLED reason=no_token")
        yield None
        return

    service = build_telegram_service()

    try:
        if settings.telegram_mode == "polling":
            polling_lock = TelegramPollingLock(token=settings.telegram_bot_token)
            if not polling_lock.acquire():
                logger.warning(
                    "TELEGRAM_POLLING_DISABLED reason=lock_held lock_path=%s",
                    polling_lock.path,
                )
                yield service
                return
            service.polling_lock = polling_lock
            await _refresh_telegram_commands_best_effort(service.bot)
            # Drop any leftover webhook so polling actually receives updates;
            # Telegram silently swallows getUpdates calls when a webhook is
            # set, which is one of the most painful local-dev footguns.
            await service.bot.delete_webhook(drop_pending_updates=True)
            logger.info("TELEGRAM_BOOT mode=polling")
            service.polling_task = asyncio.create_task(
                service.dispatcher.start_polling(service.bot, handle_signals=False),
                name="telegram-polling",
            )
        else:
            await _refresh_telegram_commands_best_effort(service.bot)
            url = settings.telegram_webhook_url
            if not url:
                raise RuntimeError("TELEGRAM_MODE=webhook requires TELEGRAM_WEBHOOK_URL to be set.")
            _validate_telegram_webhook_url(url)
            if not settings.telegram_webhook_secret:
                raise RuntimeError("TELEGRAM_MODE=webhook requires TELEGRAM_WEBHOOK_SECRET.")
            secret = settings.telegram_webhook_secret or None
            await service.bot.set_webhook(
                url=url,
                secret_token=secret,
                drop_pending_updates=True,
            )
            logger.info("TELEGRAM_BOOT mode=webhook url=%s", url)

        yield service
    finally:
        await shutdown_chat_queue_dispatcher()
        if service.polling_task is not None:
            service.polling_task.cancel()
            # The task either finishes cleanly (CancelledError) or surfaces
            # an unrelated shutdown error.  We swallow both because the
            # lifespan is already tearing down; there is nothing to recover.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await service.polling_task
        try:
            await service.bot.session.close()
        except Exception:
            logger.warning("TELEGRAM_SHUTDOWN session_close_failed", exc_info=True)
        if service.polling_lock is not None:
            service.polling_lock.release()


def _validate_telegram_webhook_url(url: str) -> None:
    """Reject webhook URLs Telegram cannot reach or that weaken local profiles."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("TELEGRAM_WEBHOOK_URL must be an HTTPS URL with a public hostname.")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".localhost"):
        raise RuntimeError("TELEGRAM_WEBHOOK_URL cannot point at localhost.")
    if hostname.endswith(".ts.net"):
        raise RuntimeError("TELEGRAM_WEBHOOK_URL cannot use a tailnet-only .ts.net hostname.")
    with contextlib.suppress(ValueError):
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise RuntimeError("TELEGRAM_WEBHOOK_URL must use a public IP or DNS hostname.")
