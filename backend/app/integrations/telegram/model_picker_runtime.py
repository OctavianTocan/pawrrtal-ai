"""aiogram runtime glue for the Telegram model picker."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from app.db import async_session_maker
from app.integrations.telegram.model_command import handle_model_command

# Re-exported so bot.py imports both via one module.
from app.integrations.telegram.model_picker import (
    MODEL_CALLBACK_PREFIX as MODEL_CALLBACK_PREFIX,  # noqa: PLC0414
)
from app.integrations.telegram.model_picker import (
    ModelButton,
    ModelCallback,
    build_host_keyboard,
    build_models_keyboard,
    build_vendor_keyboard,
    format_host_picker_text,
    format_models_picker_text,
    format_vendor_picker_text,
    get_model_picker_state,
    has_host,
    has_vendor_in_host,
    parse_model_callback_data,
    picker_not_bound_message,
    picker_stale_message,
    resolve_model_selection,
)
from app.integrations.telegram.sender import TelegramSender

if TYPE_CHECKING:
    from aiogram.types import (
        CallbackQuery,
        InlineKeyboardMarkup,
        Message,
        ReplyParameters,
    )


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
    """Open the host picker for an argument-less ``/model``."""
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
        format_host_picker_text(state.current_model_id),
        reply_markup=_inline_keyboard(build_host_keyboard()),
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

    if parsed.action == "vendors" and parsed.host is not None:
        await _edit_vendor_list(callback=callback, parsed=parsed)
        return
    if parsed.action == "list" and parsed.host is not None and parsed.provider is not None:
        await _edit_model_list(
            callback=callback, parsed=parsed, current_model_id=state.current_model_id
        )
        return

    await _edit_host_list(callback=callback, current_model_id=state.current_model_id)


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


async def _edit_vendor_list(*, callback: CallbackQuery, parsed: ModelCallback) -> None:
    if parsed.host is None or not has_host(parsed.host):
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await message.edit_text(
        format_vendor_picker_text(host=parsed.host),
        reply_markup=_inline_keyboard(build_vendor_keyboard(host=parsed.host)),
    )
    await callback.answer()


async def _edit_model_list(
    *,
    callback: CallbackQuery,
    parsed: ModelCallback,
    current_model_id: str,
) -> None:
    if (
        parsed.host is None
        or parsed.provider is None
        or not has_vendor_in_host(host=parsed.host, vendor=parsed.provider)
    ):
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    await message.edit_text(
        format_models_picker_text(host=parsed.host, vendor=parsed.provider, page=parsed.page),
        reply_markup=_inline_keyboard(
            build_models_keyboard(
                host=parsed.host,
                vendor=parsed.provider,
                page=parsed.page,
                current_model_id=current_model_id,
            )
        ),
    )
    await callback.answer()


async def _edit_host_list(*, callback: CallbackQuery, current_model_id: str) -> None:
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await message.edit_text(
        format_host_picker_text(current_model_id),
        reply_markup=_inline_keyboard(build_host_keyboard()),
    )
    await callback.answer()


def _inline_keyboard(rows: list[list[ModelButton]]) -> InlineKeyboardMarkup:
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


def _reply_parameters(message_id: int) -> ReplyParameters:
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)
