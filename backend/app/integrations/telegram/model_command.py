"""``/model`` command handler for the Telegram channel.

Supports three shapes:

- ``/model <vendor>/<model>`` — switch this conversation only.
- ``/model <vendor>/<model> default`` (or ``/model default <id>``)
  — switch this conversation **and** set the user's default model
  so future conversations inherit it.
- ``/model default`` — promote the conversation's *current* model
  to the user's default, without switching to anything else.

The aiogram glue lives in
:mod:`app.integrations.telegram.model_picker_runtime`; this module
stays framework-free and unit-testable.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.catalog import find
from app.core.providers.model_id import InvalidModelId, parse_model_id
from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    update_conversation_model,
)
from app.crud.user_preferences import set_user_default_model_id
from app.integrations.telegram.dev_admin import resolve_or_autolink_telegram_user
from app.integrations.telegram.reasoning_notify import maybe_append_model_switch_notice
from app.integrations.telegram.sender import TelegramSender

logger = logging.getLogger(__name__)

# Keyword the user types to also persist the choice as their default.
# Case-insensitive; accepts both leading- and trailing-position syntax
# (``/model default <id>`` or ``/model <id> default``).
DEFAULT_KEYWORD = "default"

_MODEL_MISSING_MESSAGE = (
    "Usage: /model &lt;vendor&gt;/&lt;model&gt; [default]\n\n"
    "The structural form is <code>[host:]vendor/model</code>; the host "
    "prefix is optional and filled in automatically.\n\n"
    "Add <code>default</code> to also set the model as your personal "
    "default for future conversations — e.g. "
    "<code>/model anthropic/claude-sonnet-4-6 default</code>."
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
_MODEL_DEFAULT_SUFFIX = " (also set as your default for future conversations ⭐)"
_MODEL_DEFAULT_ONLY_MESSAGE = (
    "Default model set to <code>{model_id}</code> ⭐\n\n"
    "Future Telegram conversations will use this model unless overridden."
)
_MODEL_DEFAULT_NO_CURRENT_MESSAGE = (
    "No current model to promote. Switch with <code>/model &lt;id&gt;</code> first, "
    "or pass an ID alongside <code>default</code>."
)
_MODEL_DEFAULT_STALE_MESSAGE = (
    "This conversation's current model (<code>{model_id}</code>) is no longer "
    "in the catalog. Pick a fresh one with <code>/model</code> first, then "
    "promote it with <code>/model default</code> — or pass an ID directly: "
    "<code>/model &lt;id&gt; default</code>."
)
_MODEL_FAIL_MESSAGE = "Couldn't update model — please try again."


@dataclass(frozen=True)
class _ParsedArgs:
    """Result of parsing the free-form text after ``/model``.

    ``model_id`` is whatever non-keyword token the user typed (still
    pre-catalog-validation) and ``make_default`` is true when the
    ``default`` keyword appeared in either leading or trailing
    position.
    """

    model_id: str
    make_default: bool


def _parse_model_args(raw: str) -> _ParsedArgs:
    """Split the optional ``default`` keyword from the model token.

    Accepted shapes:

    - ``<id> default``  → ``model_id=<id>, make_default=True``
    - ``default <id>``  → ``model_id=<id>, make_default=True``
    - ``default``       → ``model_id="", make_default=True``
    - ``<id>``          → ``model_id=<id>, make_default=False``
    - empty             → ``model_id="", make_default=False``

    Keyword match is case-insensitive. Only strips one occurrence of
    ``default`` per call — ``default default`` keeps the second as a
    parse error candidate, surfacing as ``_MODEL_UNKNOWN_MESSAGE``
    downstream.
    """
    tokens = raw.split()
    if not tokens:
        return _ParsedArgs(model_id="", make_default=False)

    make_default = False
    if tokens[0].lower() == DEFAULT_KEYWORD:
        make_default = True
        tokens = tokens[1:]
    elif tokens[-1].lower() == DEFAULT_KEYWORD:
        make_default = True
        tokens = tokens[:-1]

    model_id = " ".join(tokens).strip()
    return _ParsedArgs(model_id=model_id, make_default=make_default)


async def handle_model_command(
    *,
    sender: TelegramSender,
    model_arg: str,
    session: AsyncSession,
) -> str:
    """Process a ``/model <id> [default]`` command and persist the choice.

    Resolves the sender's binding, finds (or creates) their Telegram
    conversation, and updates ``Conversation.model_id`` so subsequent
    turns use the requested model. When the ``default`` keyword is
    present, additionally writes ``UserPreferences.default_model_id``
    so future conversations inherit the choice.

    The bare ``/model default`` shape promotes the conversation's
    current model to the user's default without switching to anything
    else.
    """
    parsed_args = _parse_model_args(model_arg)
    if not parsed_args.model_id and not parsed_args.make_default:
        return _MODEL_MISSING_MESSAGE

    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
        return _MODEL_NOT_BOUND_MESSAGE

    if parsed_args.model_id:
        return await _switch_and_maybe_default(
            sender=sender,
            session=session,
            pawrrtal_user_id=pawrrtal_user_id,
            raw_model_id=parsed_args.model_id,
            make_default=parsed_args.make_default,
        )

    return await _promote_current_to_default(
        sender=sender,
        session=session,
        pawrrtal_user_id=pawrrtal_user_id,
    )


async def _switch_and_maybe_default(
    *,
    sender: TelegramSender,
    session: AsyncSession,
    pawrrtal_user_id: uuid.UUID,
    raw_model_id: str,
    make_default: bool,
) -> str:
    """Validate + canonicalise + persist a /model <id> [default] switch."""
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

    if make_default:
        await set_user_default_model_id(
            session=session,
            user_id=pawrrtal_user_id,
            model_id=canonical_id,
        )

    logger.info(
        "TELEGRAM_MODEL_SET user_id=%s conversation_id=%s model_id=%s default=%s",
        pawrrtal_user_id,
        conversation.id,
        canonical_id,
        make_default,
    )

    base_reply = _MODEL_OK_MESSAGE.format(model_id=canonical_id)
    if make_default:
        base_reply = base_reply + _MODEL_DEFAULT_SUFFIX
    return await maybe_append_model_switch_notice(
        base_reply=base_reply,
        conversation_id=conversation.id,
        new_model_id=canonical_id,
        session=session,
    )


async def _promote_current_to_default(
    *,
    sender: TelegramSender,
    session: AsyncSession,
    pawrrtal_user_id: uuid.UUID,
) -> str:
    """Handle the bare ``/model default`` shape.

    Reads the conversation's current ``model_id``, re-validates it
    against the catalog, and writes the canonical form to
    ``UserPreferences.default_model_id``. Refuses when:

    - the conversation hasn't been pinned to anything explicit yet,
      because there'd be nothing meaningful to promote; or
    - the stored ``model_id`` is no longer in the catalog (e.g. after
      a catalog rotation removed it), because promoting a stale ID
      would silently poison every future conversation.
    """
    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    current_id = conversation.model_id
    if not current_id:
        return _MODEL_DEFAULT_NO_CURRENT_MESSAGE

    canonical_id = _canonical_catalog_id(current_id)
    if canonical_id is None:
        logger.warning(
            "TELEGRAM_DEFAULT_PROMOTE_STALE user_id=%s stale_model_id=%s",
            pawrrtal_user_id,
            current_id,
        )
        return _MODEL_DEFAULT_STALE_MESSAGE.format(model_id=current_id)

    await set_user_default_model_id(
        session=session,
        user_id=pawrrtal_user_id,
        model_id=canonical_id,
    )
    logger.info(
        "TELEGRAM_DEFAULT_MODEL_SET user_id=%s model_id=%s",
        pawrrtal_user_id,
        canonical_id,
    )
    return _MODEL_DEFAULT_ONLY_MESSAGE.format(model_id=canonical_id)


def _canonical_catalog_id(model_id: str) -> str | None:
    """Return the canonical catalog ID for ``model_id`` or ``None`` if stale."""
    try:
        parsed = parse_model_id(model_id)
    except InvalidModelId:
        return None
    entry = find(parsed)
    return None if entry is None else entry.id


async def set_user_default_model_from_callback(
    *,
    sender: TelegramSender,
    session: AsyncSession,
    canonical_model_id: str,
) -> bool:
    """Persist the user's default model from a picker callback.

    Returns ``True`` when the user was bound and the write succeeded;
    ``False`` when the sender has no binding (the picker UI shouldn't
    surface the button in that case, but we re-validate at the seam).
    """
    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
        return False
    await set_user_default_model_id(
        session=session,
        user_id=pawrrtal_user_id,
        model_id=canonical_model_id,
    )
    logger.info(
        "TELEGRAM_DEFAULT_MODEL_SET_VIA_PICKER user_id=%s model_id=%s",
        pawrrtal_user_id,
        canonical_model_id,
    )
    return True
