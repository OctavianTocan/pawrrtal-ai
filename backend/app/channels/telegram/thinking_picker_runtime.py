"""aiogram runtime glue for the Telegram thinking picker.

Mirrors :mod:`app.channels.telegram.model_picker_runtime` — keeps
the picker module framework-free so it can be unit-tested without
aiogram, while this file owns the aiogram-shaped IO.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from app.channels.crud import update_conversation_reasoning_effort
from app.channels.telegram.handlers import TelegramSender

# Re-exported so bot.py imports both via one module.
from app.channels.telegram.thinking_picker import (
    THINKING_CALLBACK_PREFIX as THINKING_CALLBACK_PREFIX,  # noqa: PLC0414
)
from app.channels.telegram.thinking_picker import (
    ThinkingButton,
    ThinkingCallback,
    ThinkingPickerState,
    build_thinking_keyboard,
    catalog_token,
    format_picker_text,
    format_unsupported_text,
    get_thinking_picker_state,
    model_supports_reasoning,
    parse_thinking_callback_data,
    picker_not_bound_message,
    picker_stale_message,
    resolve_select,
)
from app.infrastructure.database.legacy import async_session_maker

if TYPE_CHECKING:
    from aiogram.types import (
        CallbackQuery,
        InlineKeyboardMarkup,
        Message,
        ReplyParameters,
    )

_CLEAR_NOTICE = "Reasoning level cleared"


async def answer_thinking_command(*, message: Message) -> None:
    """Answer ``/thinking`` with the per-model reasoning picker."""
    sender = _sender_from_message(message)
    async with async_session_maker() as session:
        state = await get_thinking_picker_state(sender=sender, session=session)

    if state is None:
        await message.answer(
            picker_not_bound_message(),
            reply_parameters=_reply_parameters(message.message_id),
        )
        return

    if not model_supports_reasoning(state):
        await message.answer(
            format_unsupported_text(state),
            reply_parameters=_reply_parameters(message.message_id),
        )
        return

    await message.answer(
        format_picker_text(state),
        reply_markup=_inline_keyboard(build_thinking_keyboard(state)),
        reply_parameters=_reply_parameters(message.message_id),
    )


async def handle_thinking_picker_callback(*, callback: CallbackQuery) -> None:
    """Handle inline-keyboard callbacks produced by the thinking picker."""
    parsed = parse_thinking_callback_data(callback.data)
    if parsed is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        state = await get_thinking_picker_state(sender=sender, session=session)
    if state is None:
        await callback.answer(picker_not_bound_message(), show_alert=True)
        return

    if parsed.action == "clear":
        await _handle_clear(callback=callback, parsed=parsed, state=state)
        return
    if parsed.action == "select":
        await _handle_select(callback=callback, parsed=parsed, state=state)
        return
    await callback.answer(picker_stale_message(), show_alert=True)


async def _handle_select(
    *,
    callback: CallbackQuery,
    parsed: ThinkingCallback,
    state: ThinkingPickerState,
) -> None:
    """Apply a select callback, edit the message, ack the tap."""
    effort = resolve_select(parsed, entry=state.model_entry)
    if effort is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    await _persist_effort(state=state, effort=effort)
    await _refresh_picker(callback=callback, ack_text=f"Thinking: {effort}")


async def _handle_clear(
    *,
    callback: CallbackQuery,
    parsed: ThinkingCallback,
    state: ThinkingPickerState,
) -> None:
    """Clear the per-conversation override, edit the message, ack."""
    if parsed.catalog_token != catalog_token():
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    await _persist_effort(state=state, effort=None)
    await _refresh_picker(callback=callback, ack_text=_CLEAR_NOTICE)


async def _refresh_picker(*, callback: CallbackQuery, ack_text: str) -> None:
    """Re-fetch state + re-paint the keyboard so the new selection shows.

    The select / clear branches share this rendering tail. Re-fetching
    is intentional: the picker re-renders with the new "current"
    marker and a fresh clear button. The DB hit is small (one user +
    one conversation lookup) and only happens on the rare tap, not on
    every chat turn.
    """
    sender = _sender_from_callback(callback)
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    async with async_session_maker() as session:
        refreshed = await get_thinking_picker_state(sender=sender, session=session)
    if refreshed is None:
        await callback.answer(picker_not_bound_message(), show_alert=True)
        return

    await message.edit_text(
        format_picker_text(refreshed),
        reply_markup=_inline_keyboard(build_thinking_keyboard(refreshed)),
    )
    await callback.answer(ack_text)


async def _persist_effort(*, state: ThinkingPickerState, effort: str | None) -> None:
    """Persist the new override on the conversation already resolved.

    Uses ``state.conversation_id`` so we avoid a second
    user/conversation lookup round-trip — the picker has already
    resolved this in :func:`get_thinking_picker_state`.
    """
    async with async_session_maker() as session:
        await update_conversation_reasoning_effort(
            conversation_id=state.conversation_id,
            user_id=state.user_id,
            reasoning_effort=effort,
            session=session,
        )


def _inline_keyboard(rows: list[list[ThinkingButton]]) -> InlineKeyboardMarkup:
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
    # ``callback.message`` is typed ``Message | InaccessibleMessage``; the
    # hasattr() guard above narrows to the accessible Message at runtime.
    return cast("Message", message)


def _reply_parameters(message_id: int) -> ReplyParameters | None:
    if message_id <= 0:
        return None
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)
