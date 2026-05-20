"""aiogram dispatcher wiring for the Telegram bot package.

Registers slash-command handlers, callback-query handlers (model + thinking
pickers), and the plain-text message handler on a freshly-built dispatcher.
Each registration is its own function so the public ``build_telegram_service``
flow can compose them without each registration ballooning past the
project's PLR0915 cap.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.db import async_session_maker
from app.integrations.telegram.bot.state import (
    _running_tasks,
    get_bot_uptime_seconds,
    is_chat_run_active,
)
from app.integrations.telegram.bot.turn_runner import run_llm_turn

# ``TelegramSender`` is re-exported via :mod:`handlers` (which already
# imports it from :mod:`sender`) so this module imports both
# ``handle_plain_message`` and ``TelegramSender`` from the same module
# — keeps fan-out small.
from app.integrations.telegram.handlers import (
    TelegramSender,
    collect_attachments,
    handle_new_command,
    handle_plain_message,
    handle_start_command,
    handle_stop_command,
    handle_verbose_command,
)

# ``MODEL_CALLBACK_PREFIX`` is re-exported via
# :mod:`model_picker_runtime` for the same fan-out reason.
from app.integrations.telegram.model_picker_runtime import (
    MODEL_CALLBACK_PREFIX,
    answer_model_command,
    handle_model_picker_callback,
)

# ``compact_command`` is re-exported via :mod:`status` to keep fan-out
# small (same trick as ``handle_lcm_command``).
from app.integrations.telegram.status import (
    handle_compact_command,
    handle_lcm_command,
    handle_status_command,
)

# ``THINKING_CALLBACK_PREFIX`` is re-exported via
# :mod:`thinking_picker_runtime` for the same fan-out reason.
from app.integrations.telegram.thinking_picker_runtime import (
    THINKING_CALLBACK_PREFIX,
    answer_thinking_command,
    handle_thinking_picker_callback,
)

if TYPE_CHECKING:
    from aiogram import Dispatcher
    from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)

_START_COMMAND_PARTS_WITH_PAYLOAD = 2
"""``"/start <code>"`` splits into exactly two parts; below this means no payload."""


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


def _extract_start_payload(text: str) -> str | None:
    """Return the argument after ``/start`` (Telegram deep-link payload), if any."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < _START_COMMAND_PARTS_WITH_PAYLOAD:
        return None
    return parts[1].strip() or None


def register_telegram_command_handlers(dispatcher: Dispatcher) -> None:
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
        await answer_model_command(message=message, model_arg=model_arg)

    @dispatcher.message(Command("thinking"))
    async def _on_thinking(message: Message) -> None:
        await answer_thinking_command(message=message)

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

    _register_telegram_lcm_command_handlers(dispatcher)


def _register_telegram_lcm_command_handlers(dispatcher: Dispatcher) -> None:
    """Register LCM-flavoured commands (``/lcm`` + ``/compact``).

    Split out of :func:`register_telegram_command_handlers` so that
    function stays under the project's PLR0915 cap and so the LCM
    surface lives in one place when future LCM commands land.
    """
    from aiogram.filters import Command  # noqa: PLC0415

    @dispatcher.message(Command("lcm"))
    async def _on_lcm(message: Message) -> None:
        # Diagnostic surface for Lossless Context Management — closes #303.
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


def register_telegram_callback_handlers(dispatcher: Dispatcher) -> None:
    """Register inline-keyboard callback handlers on the aiogram dispatcher."""

    @dispatcher.callback_query(lambda query: (query.data or "").startswith(MODEL_CALLBACK_PREFIX))
    async def _on_model_picker(callback: CallbackQuery) -> None:
        await handle_model_picker_callback(callback=callback)

    @dispatcher.callback_query(
        lambda query: (query.data or "").startswith(THINKING_CALLBACK_PREFIX)
    )
    async def _on_thinking_picker(callback: CallbackQuery) -> None:
        await handle_thinking_picker_callback(callback=callback)


def register_telegram_message_handler(dispatcher: Dispatcher) -> None:
    """Register the plain text chat handler on the aiogram dispatcher."""

    @dispatcher.message()
    async def _on_message(message: Message) -> None:
        # Collect inbound attachments BEFORE deciding to skip the message.
        # An image-only message (no text) is still a real turn now (#305).
        # Voice / documents become text annotations so the agent has
        # metadata to act on (partial #304 / #305 — full STT + markitdown
        # extraction land in follow-up PRs).  ``collect_attachments`` is
        # re-exported through ``handlers`` so this module doesn't pick up
        # an extra fan-out edge that would push it over sentrux's
        # ``no_god_files`` ceiling — see #281's ADR for the long-term
        # registry split.
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

        await run_llm_turn(
            message=message,
            context=result,
            images=attachments.images if attachments is not None else None,
            text_annotations=(attachments.text_annotations if attachments is not None else None),
        )
