"""``/model`` command handler — pulled out of ``handlers.py``.

Moved here so ``handlers.py`` stays under the project's 500-line file
budget after the reasoning-effort backstop landed. The command itself
is unchanged: parse → catalog-validate → persist → maybe-append
reasoning-effort notice.

Imported by :mod:`app.integrations.telegram.model_picker_runtime`
(the aiogram glue) and indirectly reached from ``bot.py`` through
``answer_model_command``.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.catalog import find
from app.core.providers.model_id import InvalidModelId, parse_model_id
from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    update_conversation_model,
)
from app.integrations.telegram.dev_admin import resolve_or_autolink_telegram_user
from app.integrations.telegram.reasoning_notify import maybe_append_model_switch_notice
from app.integrations.telegram.sender import TelegramSender

logger = logging.getLogger(__name__)

_MODEL_MISSING_MESSAGE = (
    "Usage: /model &lt;vendor&gt;/&lt;model&gt;\n\n"
    "The structural form is <code>[host:]vendor/model</code>; the host "
    "prefix is optional and filled in automatically."
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
    """Process a ``/model <id>`` command and persist the model override.

    Resolves the sender's binding, finds (or creates) their Telegram
    conversation, and updates ``Conversation.model_id`` so subsequent
    turns use the requested model. When the new model honours a
    different set of reasoning levels than the stored one, the
    shared backstop appends a notice describing the change.
    """
    raw = model_arg.strip()
    if not raw:
        return _MODEL_MISSING_MESSAGE

    try:
        parsed = parse_model_id(raw)
    except InvalidModelId as exc:
        return _MODEL_INVALID_MESSAGE.format(raw=raw, reason=str(exc))
    entry = find(parsed)
    if entry is None:
        return _MODEL_UNKNOWN_MESSAGE.format(raw=raw)

    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
        return _MODEL_NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )

    # Store the canonical "host:vendor/model" form regardless of how
    # the user typed it, so stored model_ids stay consistent.
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
    return await maybe_append_model_switch_notice(
        base_reply=_MODEL_OK_MESSAGE.format(model_id=canonical_id),
        conversation_id=conversation.id,
        new_model_id=canonical_id,
        session=session,
    )
