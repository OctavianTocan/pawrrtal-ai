"""aiogram-backed Telegram bot service.

Thin glue between aiogram's ``Bot`` + ``Dispatcher`` and the framework-free
handlers in :mod:`app.integrations.telegram.handlers`. Two boot modes:

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
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.channels import resolve_channel
from app.channels.base import ChannelMessage
from app.channels.telegram import SURFACE_TELEGRAM, make_telegram_sender
from app.channels.turn_runner import ChatTurnInput, run_turn
from app.core.agent_tools import build_agent_tools
from app.core.config import settings
from app.crud.workspace import get_default_workspace
from app.db import async_session_maker
from app.integrations.telegram.bot_permissions import build_telegram_permission_check
from app.integrations.telegram.bot_provider_resolution import (
    resolve_provider_with_auto_clear,
)
from app.integrations.telegram.handlers import (
    TelegramSender,
    TelegramTurnContext,
    handle_model_command,
    handle_new_command,
    handle_plain_message,
    handle_start_command,
    handle_status_command,
    handle_stop_command,
    handle_verbose_command,
)

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.types import Message, Update

logger = logging.getLogger(__name__)

_TELEGRAM_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Connect your Pawrrtal account"),
    ("new", "Start a new conversation"),
    ("model", "Switch the model for this conversation"),
    ("verbose", "Set detail level: 0 quiet, 1 tools, 2 thinking"),
    ("stop", "Stop the active run"),
    ("status", "Show gateway + conversation status"),
)

# Captured at module import so /status can report this worker's uptime
# without reading the wall clock at boot. Process-local — multi-worker
# deployments report only the worker that handled the command.
_BOT_START_MONOTONIC: float = time.monotonic()


def get_bot_uptime_seconds() -> float:
    """Return seconds since this worker's process started."""
    return time.monotonic() - _BOT_START_MONOTONIC


def is_chat_run_active(chat_id: int) -> bool:
    """Return whether an agent run is in flight for ``chat_id`` on this worker."""
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
_running_tasks: dict[int, asyncio.Task[None]] = {}


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
    refresh = float(settings.telegram_typing_refresh_seconds)
    try:
        while True:
            await _send_one_typing_action(bot, chat_id, thread_id)
            await asyncio.sleep(refresh)
    except asyncio.CancelledError:
        return


# TODO: This is pretty nonsensical. We have a custom entire chat impkementation that just duplicates the logic here.
async def _run_llm_turn(*, message: Message, context: TelegramTurnContext) -> None:
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
    """
    user_text = message.text or ""
    if message.bot is None:
        raise RuntimeError("Telegram message has no bot; refusing to stream.")
    thinking_msg = await message.answer("⏳")

    async with async_session_maker() as ws_session:
        workspace = await get_default_workspace(context.nexus_user_id, ws_session)

    tg_sender = make_telegram_sender(
        message.bot,
        message.chat.id,
        message_thread_id=context.thread_id,
    )
    agent_tools = (
        build_agent_tools(
            workspace_root=Path(workspace.path),
            user_id=context.nexus_user_id,
            send_fn=tg_sender,
            surface="telegram",
        )
        if workspace is not None
        else []
    )

    provider, warning = await resolve_provider_with_auto_clear(
        context,
        workspace_root=Path(workspace.path) if workspace is not None else None,
    )
    if warning is not None:
        await message.answer(warning)

    channel_message: ChannelMessage = {
        "user_id": context.nexus_user_id,
        "conversation_id": context.conversation_id,
        "text": user_text,
        "surface": SURFACE_TELEGRAM,
        "model_id": context.model_id,
        "metadata": {
            "bot": message.bot,
            "chat_id": message.chat.id,
            "message_id": thinking_msg.message_id,
        },
    }
    turn_input = ChatTurnInput(
        conversation_id=context.conversation_id,
        user_id=context.nexus_user_id,
        question=user_text,
        provider=provider,
        channel=resolve_channel(SURFACE_TELEGRAM),
        channel_message=channel_message,
        workspace_root=Path(workspace.path) if workspace is not None else None,
        tools=agent_tools,
        permission_check=build_telegram_permission_check(
            context,
            Path(workspace.path) if workspace is not None else None,
        ),
        log_tag="TELEGRAM",
        log_extras={"chat_id": message.chat.id},
        verbose_level=(
            context.verbose_level
            if context.verbose_level is not None
            else settings.telegram_verbose_default
        ),
    )

    async def _do_stream() -> None:
        async for _ in run_turn(turn_input):
            pass

    # Cancel any previous stream for this chat before starting the new one.
    chat_id = message.chat.id
    old_task = _running_tasks.pop(chat_id, None)
    if old_task is not None and not old_task.done():
        old_task.cancel()

    # PR 07: persistent typing indicator. Telegram clears the
    # "typing…" status after ~5 seconds, so we refresh on a timer
    # for the whole duration of the agent run. Cancelled in the
    # finally block alongside the stream task so a chat that
    # finished (or was /stop'd) doesn't keep the indicator up.
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

    async def feed_webhook_update(self, update: Update) -> None:
        """Hand a single ``Update`` parsed from the webhook body to aiogram.

        Used by the FastAPI webhook route in production. Polling does
        not call this — aiogram's polling loop owns its own dispatch.
        """
        await self.dispatcher.feed_update(self.bot, update)


def build_telegram_service() -> TelegramService:  # noqa: PLR0915 — single dispatcher-registration body; splitting fragments shared `dispatcher` closure
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
    from aiogram.filters import Command, CommandStart  # noqa: PLC0415

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be set to start the Telegram service.")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

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
        text = message.text or ""
        # Strip the "/model" prefix (plus optional @botname) and grab the rest.
        parts = text.strip().split(maxsplit=1)
        model_arg = parts[1].strip() if len(parts) > 1 else ""
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            reply = await handle_model_command(sender=sender, model_arg=model_arg, session=session)
        await message.answer(reply)

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

    @dispatcher.message()
    async def _on_message(message: Message) -> None:
        if not message.text:
            return
        sender = _sender_from_message(message)
        async with async_session_maker() as session:
            result = await handle_plain_message(sender=sender, text=message.text, session=session)

        if isinstance(result, str):
            # Terminal reply — user isn't bound or some other error.
            await message.answer(result)
            return

        await _run_llm_turn(message=message, context=result)

    return TelegramService(bot=bot, dispatcher=dispatcher)


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
    try:
        await refresh_telegram_commands(bot)
    except Exception:
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
    await _refresh_telegram_commands_best_effort(service.bot)

    if settings.telegram_mode == "polling":
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
        url = settings.telegram_webhook_url
        if not url:
            raise RuntimeError("TELEGRAM_MODE=webhook requires TELEGRAM_WEBHOOK_URL to be set.")
        secret = settings.telegram_webhook_secret or None
        await service.bot.set_webhook(
            url=url,
            secret_token=secret,
            drop_pending_updates=True,
        )
        logger.info("TELEGRAM_BOOT mode=webhook url=%s", url)

    try:
        yield service
    finally:
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
