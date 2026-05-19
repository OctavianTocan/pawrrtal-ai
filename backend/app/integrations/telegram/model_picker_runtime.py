"""aiogram runtime glue for the Telegram model picker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db import async_session_maker
from app.integrations.telegram.handlers import TelegramSender, handle_model_command
from app.integrations.telegram.model_picker import (
    ModelButton,
    ModelCallback,
    build_models_keyboard,
    format_models_picker_text,
    get_model_picker_state,
    parse_model_callback_data,
    picker_not_bound_message,
    picker_stale_message,
    resolve_model_selection,
)
from app.integrations.telegram.model_picker import (
    build_host_keyboard as build_provider_keyboard,  # TODO: removed in Task 5
)
from app.integrations.telegram.model_picker import (
    format_host_picker_text as format_provider_picker_text,  # TODO: removed in Task 5
)
from app.integrations.telegram.model_picker import (
    has_host as has_provider,  # TODO: removed in Task 5
)

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message


async def answer_model_command(*, message: Message, model_arg: str) -> None:
    """Answer ``/model`` with either the picker or typed-model update."""
    if _opens_picker(model_arg):
        await answer_model_picker(message=message)
        return

    sender = _sender_from_message(message)
    async with async_session_maker() as session:
        reply = await handle_model_command(sender=sender, model_arg=model_arg, session=session)
    await message.answer(reply, reply_parameters=_reply_parameters(message.message_id))


async def answer_model_picker(*, message: Message) -> None:
    """Open the provider picker for ``/models`` or empty ``/model``."""
    sender = _sender_from_message(message)
    async with async_session_maker() as session:
        state = await get_model_picker_state(sender=sender, session=session)

    if state is None:
        await message.answer(
            picker_not_bound_message(),
            reply_parameters=_reply_parameters(message.message_id),
        )
        return

    await message.answer(
        format_provider_picker_text(state.current_model_id),
        reply_markup=_inline_keyboard(build_provider_keyboard()),
        reply_parameters=_reply_parameters(message.message_id),
    )


async def handle_model_picker_callback(*, callback: CallbackQuery) -> None:
    """Handle inline keyboard callbacks produced by the model picker."""
    parsed = parse_model_callback_data(callback.data)
    if parsed is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    if parsed.action == "select":
        await _handle_model_select(callback=callback, parsed=parsed)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        state = await get_model_picker_state(sender=sender, session=session)
    if state is None:
        await callback.answer(picker_not_bound_message(), show_alert=True)
        return

    if parsed.action == "list" and parsed.provider is not None:
        await _edit_model_list(
            callback=callback, parsed=parsed, current_model_id=state.current_model_id
        )
        return

    await _edit_provider_list(callback=callback, current_model_id=state.current_model_id)


def _opens_picker(model_arg: str) -> bool:
    return model_arg.strip().lower() in {"", "list"}


async def _handle_model_select(*, callback: CallbackQuery, parsed: ModelCallback) -> None:
    entry = resolve_model_selection(parsed)
    if entry is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        reply = await handle_model_command(sender=sender, model_arg=entry.id, session=session)
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await message.edit_text(reply)
    await callback.answer(f"Model set: {entry.short_name}")


async def _edit_model_list(
    *,
    callback: CallbackQuery,
    parsed: ModelCallback,
    current_model_id: str,
) -> None:
    if parsed.provider is None or not has_provider(parsed.provider):
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    await message.edit_text(
        format_models_picker_text(provider=parsed.provider, page=parsed.page),
        reply_markup=_inline_keyboard(
            build_models_keyboard(
                provider=parsed.provider,
                page=parsed.page,
                current_model_id=current_model_id,
            )
        ),
    )
    await callback.answer()


async def _edit_provider_list(*, callback: CallbackQuery, current_model_id: str) -> None:
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await message.edit_text(
        format_provider_picker_text(current_model_id),
        reply_markup=_inline_keyboard(build_provider_keyboard()),
    )
    await callback.answer()


def _inline_keyboard(rows: list[list[ModelButton]]) -> object:
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
