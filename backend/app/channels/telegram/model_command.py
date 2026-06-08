"""``/model`` command handler for the Telegram channel.

Supports a single shape:

- ``/model <vendor>/<model>`` — switch this conversation's model.

Argument-less ``/model`` opens the inline picker instead; that glue
lives in :mod:`app.channels.telegram.model_picker_runtime`. This module
stays framework-free and unit-testable.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import (
    get_or_create_telegram_conversation_full,
)
from app.channels.telegram.dev_admin import resolve_or_autolink_telegram_user
from app.channels.telegram.reasoning_notify import maybe_append_model_switch_notice
from app.channels.telegram.sender import TelegramSender
from app.conversations.settings import update_conversation_model
from app.providers.catalog import find
from app.providers.model_id import InvalidModelId, parse_model_id

logger = logging.getLogger(__name__)

_MODEL_MISSING_MESSAGE = (
    "Usage: /model &lt;vendor&gt;/&lt;model&gt;\n\n"
    "The structural form is <code>[host:]vendor/model</code>; the host "
    "prefix is optional and filled in automatically.\n\n"
    "Use /model (no arguments) to pick from the configured models."
)
_MODEL_INVALID_MESSAGE = (
    "Couldn't parse <code>{raw}</code> as a model ID ({reason}).\n\n"
    "Expected structural form: <code>[host:]vendor/model</code>."
)
_MODEL_UNKNOWN_MESSAGE = (
    "I don't have <code>{raw}</code> in the model catalog.\n\n"
    "Use /model (no arguments) to pick one of the configured models."
)
_MODEL_NOT_BOUND_MESSAGE = "You need to connect your account first before switching models."
_MODEL_OK_MESSAGE = "Model switched to <code>{model_id}</code> ✅"
_MODEL_FAIL_MESSAGE = "Couldn't update model — please try again."


async def handle_model_command(
    *,
    sender: TelegramSender,
    model_arg: str,
    session: AsyncSession,
) -> str:
    """Process a ``/model <id>`` command and persist the switch.

    Resolves the sender's binding, finds (or creates) their Telegram
    conversation, and updates ``Conversation.model_id`` so subsequent
    turns use the requested model.
    """
    raw_model_id = model_arg.strip()
    if not raw_model_id:
        return _MODEL_MISSING_MESSAGE

    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
        return _MODEL_NOT_BOUND_MESSAGE

    return await _switch_model(
        sender=sender,
        session=session,
        pawrrtal_user_id=pawrrtal_user_id,
        raw_model_id=raw_model_id,
    )


async def _switch_model(
    *,
    sender: TelegramSender,
    session: AsyncSession,
    pawrrtal_user_id: uuid.UUID,
    raw_model_id: str,
) -> str:
    """Validate + canonicalise + persist a ``/model <id>`` switch."""
    try:
        parsed = parse_model_id(raw_model_id)
    except InvalidModelId as exc:
        return _MODEL_INVALID_MESSAGE.format(raw=raw_model_id, reason=str(exc))
    entry = find(parsed)
    if entry is None:
        return _MODEL_UNKNOWN_MESSAGE.format(raw=raw_model_id)

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )

    # Store the canonical "host:vendor/model" form regardless of how
    # the user typed it, so persisted model_ids stay consistent.
    canonical_id = entry.id
    updated = await update_conversation_model(
        conversation_id=conversation.id,
        model_id=canonical_id,
        session=session,
    )
    if not updated:
        logger.warning(
            "TELEGRAM_MODEL_UPDATE_FAILED conversation_id=%s model_id=%s",
            conversation.id,
            canonical_id,
        )
        return _MODEL_FAIL_MESSAGE

    logger.info(
        "TELEGRAM_MODEL_SET user_id=%s conversation_id=%s model_id=%s",
        pawrrtal_user_id,
        conversation.id,
        canonical_id,
    )

    base_reply = _MODEL_OK_MESSAGE.format(model_id=canonical_id)
    return await maybe_append_model_switch_notice(
        base_reply=base_reply,
        conversation_id=conversation.id,
        new_model_id=canonical_id,
        session=session,
    )
