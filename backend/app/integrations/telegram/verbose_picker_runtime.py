"""aiogram runtime glue for the Telegram verbose-level picker.

Mirrors :mod:`app.integrations.telegram.thinking_picker_runtime` —
keeps the picker module framework-free so it can be unit-tested
without aiogram, while this file owns the aiogram-shaped IO.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.crud.channel import update_conversation_verbose_level
from app.db import async_session_maker
from app.integrations.telegram.handlers import TelegramSender
from app.integrations.telegram.verbose_picker import (
    VERBOSE_CALLBACK_PREFIX,  # noqa: F401  # re-exported so bot.py imports both via one module
    VerboseButton,
    VerboseCallback,
    VerbosePickerState,
    build_verbose_keyboard,
    format_picker_text,
    get_verbose_picker_state,
    parse_verbose_callback_data,
    picker_not_bound_message,
    picker_stale_message,
    verbose_label,
)

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

_CLEAR_NOTICE = "Verbose override cleared"


async def answer_verbose_command(*, message: Message) -> None:
    """Answer ``/verbose`` (no arg) with the per-conversation picker."""
    sender = _sender_from_message(message)
    async with async_session_maker() as session:
        state = await get_verbose_picker_state(
            sender=sender,
            session=session,
            default_level=settings.telegram_verbose_default,
        )

    if state is None:
        await message.answer(
            picker_not_bound_message(),
            reply_parameters=_reply_parameters(message.message_id),
        )
        return

    await message.answer(
        format_picker_text(state),
        reply_markup=_inline_keyboard(build_verbose_keyboard(state)),
        reply_parameters=_reply_parameters(message.message_id),
    )


async def handle_verbose_picker_callback(*, callback: CallbackQuery) -> None:
    """Handle inline-keyboard callbacks produced by the verbose picker."""
    parsed = parse_verbose_callback_data(callback.data)
    if parsed is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        state = await get_verbose_picker_state(
            sender=sender,
            session=session,
            default_level=settings.telegram_verbose_default,
        )
    if state is None:
        await callback.answer(picker_not_bound_message(), show_alert=True)
        return

    if parsed.action == "clear":
        await _handle_clear(callback=callback, state=state)
        return
    if parsed.action == "select" and parsed.level is not None:
        await _handle_select(callback=callback, parsed=parsed, state=state)
        return
    await callback.answer(picker_stale_message(), show_alert=True)


async def _handle_select(
    *,
    callback: CallbackQuery,
    parsed: VerboseCallback,
    state: VerbosePickerState,
) -> None:
    """Apply a select callback, edit the message, ack the tap."""
    if parsed.level is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await _persist_level(state=state, level=parsed.level)
    await _refresh_picker(
        callback=callback,
        ack_text=f"Verbose: {parsed.level} ({verbose_label(parsed.level)})",
    )


async def _handle_clear(
    *,
    callback: CallbackQuery,
    state: VerbosePickerState,
) -> None:
    """Clear the per-conversation override, edit the message, ack."""
    # ``state`` is unused here today — the persist path doesn't need
    # the previous value — but we keep the parameter so the function
    # mirrors the select handler. Picker state is re-fetched inside
    # ``_refresh_picker`` regardless.
    del state
    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        refreshed = await get_verbose_picker_state(
            sender=sender,
            session=session,
            default_level=settings.telegram_verbose_default,
        )
    if refreshed is None:
        await callback.answer(picker_not_bound_message(), show_alert=True)
        return
    await _persist_level(state=refreshed, level=None)
    await _refresh_picker(callback=callback, ack_text=_CLEAR_NOTICE)


async def _refresh_picker(*, callback: CallbackQuery, ack_text: str) -> None:
    """Re-fetch state + re-paint the keyboard so the new selection shows."""
    sender = _sender_from_callback(callback)
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    async with async_session_maker() as session:
        refreshed = await get_verbose_picker_state(
            sender=sender,
            session=session,
            default_level=settings.telegram_verbose_default,
        )
    if refreshed is None:
        await callback.answer(picker_not_bound_message(), show_alert=True)
        return

    await message.edit_text(
        format_picker_text(refreshed),
        reply_markup=_inline_keyboard(build_verbose_keyboard(refreshed)),
    )
    await callback.answer(ack_text)


async def _persist_level(*, state: VerbosePickerState, level: int | None) -> None:
    """Persist the new verbose level on the conversation."""
    async with async_session_maker() as session:
        await update_conversation_verbose_level(
            conversation_id=state.conversation_id,
            verbose_level=level,
            session=session,
        )


def _inline_keyboard(rows: list[list[VerboseButton]]) -> object:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=button.text, callback_data=button.callback_data)
                for button in row
            ]
            for row in rows
        ]
    )


def _sender_from_message(message: Message) -> TelegramSender:
    user = message.from_user
    if user is None:
        raise RuntimeError("Telegram message has no from_user; refusing to dispatch.")
    return TelegramSender(
        user_id=user.id,
        chat_id=message.chat.id,
        username=user.username,
        full_name=user.full_name,
        thread_id=message.message_thread_id,
    )


def _sender_from_callback(callback: CallbackQuery) -> TelegramSender:
    message = _callback_message(callback)
    if message is None:
        raise RuntimeError("Telegram callback has no accessible message.")
    user = callback.from_user
    return TelegramSender(
        user_id=user.id,
        chat_id=message.chat.id,
        username=user.username,
        full_name=user.full_name,
        thread_id=message.message_thread_id,
    )


def _callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    if message is None or not hasattr(message, "edit_text"):
        return None
    return message


def _reply_parameters(message_id: int) -> object:
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)
