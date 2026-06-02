"""aiogram runtime glue for the Telegram ``/config`` picker."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from app.channels.telegram.config_picker import (
    CONFIG_CALLBACK_PREFIX as CONFIG_CALLBACK_PREFIX,  # noqa: PLC0414
)
from app.channels.telegram.config_picker import (
    ConfigButton,
    ConfigCallback,
    ConfigPickerState,
    config_not_bound_message,
    config_stale_message,
    current_value_for_toggle,
    env_key_for_toggle,
    format_config_text,
    get_config_picker_state,
    parse_config_callback_data,
    toggle_label,
)
from app.channels.telegram.handlers import TelegramSender
from app.infrastructure.database.legacy import async_session_maker
from app.infrastructure.keys import load_workspace_env, save_workspace_env

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyParameters


async def answer_config_command(*, message: Message) -> None:
    """Answer ``/config`` with a workspace-scoped toggle panel."""
    sender = _sender_from_message(message)
    async with async_session_maker() as session:
        state = await get_config_picker_state(sender=sender, session=session)

    if state is None:
        await message.answer(
            config_not_bound_message(),
            reply_parameters=_reply_parameters(message.message_id),
        )
        return

    await message.answer(
        format_config_text(state),
        reply_markup=_inline_keyboard(_keyboard_rows(state)),
        reply_parameters=_reply_parameters(message.message_id),
    )


async def handle_config_picker_callback(*, callback: CallbackQuery) -> None:
    """Handle inline-keyboard callbacks produced by the config picker."""
    parsed = parse_config_callback_data(callback.data)
    if parsed is None:
        await callback.answer(config_stale_message(), show_alert=True)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        state = await get_config_picker_state(sender=sender, session=session)
    if state is None:
        await callback.answer(config_not_bound_message(), show_alert=True)
        return

    await _persist_toggle(parsed=parsed, state=state)
    await _refresh_picker(callback=callback, parsed=parsed)


async def _persist_toggle(*, parsed: ConfigCallback, state: ConfigPickerState) -> None:
    """Flip one workspace env toggle for the resolved state."""
    env = load_workspace_env(state.workspace_root)
    current = current_value_for_toggle(state, parsed.toggle)
    env[env_key_for_toggle(parsed.toggle)] = "false" if current else "true"
    save_workspace_env(state.workspace_root, env)


async def _refresh_picker(*, callback: CallbackQuery, parsed: ConfigCallback) -> None:
    """Re-fetch and repaint the picker after a toggle."""
    message = _callback_message(callback)
    if message is None:
        await callback.answer(config_stale_message(), show_alert=True)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        refreshed = await get_config_picker_state(sender=sender, session=session)
    if refreshed is None:
        await callback.answer(config_not_bound_message(), show_alert=True)
        return

    value = current_value_for_toggle(refreshed, parsed.toggle)
    await message.edit_text(
        format_config_text(refreshed),
        reply_markup=_inline_keyboard(_keyboard_rows(refreshed)),
    )
    await callback.answer(f"{toggle_label(parsed.toggle)}: {'On' if value else 'Off'}")


def _keyboard_rows(state: ConfigPickerState) -> list[list[ConfigButton]]:
    from app.channels.telegram.config_picker import build_config_keyboard  # noqa: PLC0415

    return build_config_keyboard(state)


def _inline_keyboard(rows: list[list[ConfigButton]]) -> InlineKeyboardMarkup:
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


def _reply_parameters(message_id: int) -> ReplyParameters:
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)


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
    return cast("Message", message)
