"""Inbound message handlers for the Telegram channel adapter.

Kept deliberately framework-thin so the same logic can be exercised from a
unit test without spinning up aiogram.  Each handler returns either a plain
string (for terminal error replies the bot sends immediately) or a
``TelegramTurnContext`` when the message should be routed to the LLM pipeline.

The split is what makes Telegram features testable locally — see
``tests/integrations/test_telegram.py``.

Handler states
--------------
1. The user sent ``/start <code>`` — redeem the code and confirm the bind.
2. The user sent a plain message **and** has a binding — return a
   ``TelegramTurnContext`` so ``bot.py`` can route to the LLM via the
   channel abstraction.
3. The user sent a plain message but is **not** bound — return the
   onboarding nudge string.
4. The user sent ``/stop`` — abort the entire active agent run
   (cancels the underlying ``asyncio.Task`` so the LLM call, any
   in-flight tool calls, and the SSE delivery all stop together).
   See ``bot.py``'s ``_running_tasks`` for the cancellation plumbing.
5. The user sent ``/model <id>`` — switch the session model.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.catalog import default_model, find
from app.core.providers.model_id import InvalidModelId, parse_model_id
from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    get_user_id_for_external,
    redeem_link_code,
    update_conversation_model,
    update_conversation_verbose_level,
)

# Loose match for the link-code shape (8 chars from the look-alike-free
# alphabet defined in app.crud.channel). Used to distinguish "user pasted
# a code" from "user is talking to an unbound bot" so we can redeem the
# former and nudge the latter.
_CODE_SHAPE = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8}$")

logger = logging.getLogger(__name__)

PROVIDER = "telegram"

# Reply strings — centralized here so copy review doesn't require tracing
# through the dispatcher.
_NOT_BOUND_MESSAGE = (
    "Hey 👋 I don't recognize this Telegram account yet.\n\n"
    "To connect it, log in on the web app, open Settings → Channels, "
    "click 'Connect Telegram', and either tap the deep link or send me "
    "the code you'll see there."
)
_BIND_OK_MESSAGE = "Connected ✅ — you can now chat with Nexus from here."
_BIND_BAD_CODE_MESSAGE = (
    "That code didn't work. It may have expired (codes live for 10 minutes) "
    "or already been used. Generate a fresh one from Settings → Channels."
)
# Worded as "Stopped" not "Stream stopped" because /stop cancels the
# entire agent run — LLM call + tools + delivery — not just the SSE
# stream.  Cancellation propagates through `asyncio.Task.cancel()` to
# every `await` point in the run.
_STOP_STOPPED_MESSAGE = "⏹ Stopped."
_STOP_NOTHING_MESSAGE = "Nothing is running right now."
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
    "Use /models to pick one of the configured models."
)
_MODEL_NOT_BOUND_MESSAGE = "You need to connect your account first before switching models."
_MODEL_OK_MESSAGE = "Model switched to <code>{model_id}</code> ✅"
_MODEL_FAIL_MESSAGE = "Couldn't update model — please try again."
_NEW_NOT_BOUND_MESSAGE = "Connect your account first before starting a new conversation."
_NEW_OK_MESSAGE = "✨ New conversation started. What's on your mind?"

# /verbose handler copy
_VERBOSE_USAGE_MESSAGE = (
    "Usage: <code>/verbose 0|1|2</code>\n\n"
    "0 = quiet (final answer only)\n"
    "1 = normal (show tool calls inline)\n"
    "2 = detailed (show tool calls + chain-of-thought)"
)
_VERBOSE_NOT_BOUND_MESSAGE = "Connect your account first before changing the verbose level."
_VERBOSE_OK_MESSAGE = "Verbose level set to {level} ({label})."
_VERBOSE_FAIL_MESSAGE = "Couldn't update verbose level — please try again."

# Human-readable labels used in the /verbose reply.
_VERBOSE_LABELS: dict[int, str] = {
    0: "quiet",
    1: "normal",
    2: "detailed",
}


@dataclass(frozen=True)
class TelegramSender:
    """Stable subset of an aiogram ``Message.from_user`` we need.

    Modeled as a plain dataclass so handler tests don't have to import aiogram
    or build a fake bot.
    """

    user_id: int
    chat_id: int
    username: str | None
    full_name: str | None
    # Telegram Bot API 9.3+ topic thread ID.  None when topics not enabled.
    thread_id: int | None = None


@dataclass(frozen=True)
class TelegramTurnContext:
    """Resolved context for routing a Telegram message to the LLM pipeline.

    Returned by ``handle_plain_message`` when the sender has a valid binding.
    ``bot.py`` uses this to build the ``ChannelMessage`` and invoke the
    channel delivery loop.
    """

    nexus_user_id: uuid.UUID
    """Nexus user UUID resolved from the channel binding."""

    conversation_id: uuid.UUID
    """Stable Nexus conversation for this Telegram user."""

    model_id: str
    """Model to use for this turn (default or conversation override)."""

    thread_id: int | None = None
    """Telegram topic thread ID, forwarded from the sender. None for plain DMs."""

    verbose_level: int | None = None
    """Per-conversation verbose level (PR 07): None inherits the global
    default ``settings.telegram_verbose_default``; 0/1/2 override."""


async def handle_start_command(
    *,
    sender: TelegramSender,
    payload: str | None,
    session: AsyncSession,
) -> str:
    """Process ``/start`` (with or without a binding code) inbound update.

    When a code is included (Telegram delivers the deep-link argument as the
    first text after ``/start``), redeem it and produce the bind confirmation.
    Without one, fall back to the not-bound nudge.

    Args:
        sender: Normalized sender identity.
        payload: Text after ``/start``, if any (the binding code).
        session: Async database session.

    Returns:
        Reply string the bot should send immediately.
    """
    code = (payload or "").strip()
    if not code:
        return _NOT_BOUND_MESSAGE

    binding = await redeem_link_code(
        code=code,
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        external_chat_id=str(sender.chat_id),
        display_handle=sender.username or sender.full_name,
        session=session,
    )
    if binding is None:
        return _BIND_BAD_CODE_MESSAGE

    logger.info(
        "TELEGRAM_BIND_OK external_user_id=%s nexus_user_id=%s",
        sender.user_id,
        binding.user_id,
    )
    return _BIND_OK_MESSAGE


async def handle_plain_message(
    *,
    sender: TelegramSender,
    text: str,
    session: AsyncSession,
) -> str | TelegramTurnContext:
    """Process a non-command message from a Telegram chat.

    Returns a string when the message can be replied to immediately (e.g. the
    user isn't bound yet), or a ``TelegramTurnContext`` when the message
    should be routed to the LLM pipeline.  The bot dispatcher calls this,
    inspects the result, and either sends the string directly or drives the
    channel streaming loop.

    Args:
        sender: Normalized sender identity.
        text: User's message text.
        session: Async database session.

    Returns:
        ``str`` for immediate replies, ``TelegramTurnContext`` for LLM routing.
    """
    nexus_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if nexus_user_id is None:
        # The not-bound nudge tells the user to "send me the code" — so
        # if a plain message looks like one, try to redeem it here
        # instead of forcing them through the /start deep link. We only
        # match the exact code shape so we don't accidentally treat
        # arbitrary chatter as a redemption attempt.
        candidate = text.strip().upper()
        if _CODE_SHAPE.fullmatch(candidate):
            binding = await redeem_link_code(
                code=candidate,
                provider=PROVIDER,
                external_user_id=str(sender.user_id),
                external_chat_id=str(sender.chat_id),
                display_handle=sender.username or sender.full_name,
                session=session,
            )
            if binding is not None:
                logger.info(
                    "TELEGRAM_BIND_OK_VIA_PLAIN external_user_id=%s nexus_user_id=%s",
                    sender.user_id,
                    binding.user_id,
                )
                return _BIND_OK_MESSAGE
            return _BIND_BAD_CODE_MESSAGE
        return _NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=nexus_user_id,
        session=session,
        thread_id=sender.thread_id,
    )

    model_id = conversation.model_id or default_model().id

    logger.info(
        "TELEGRAM_TURN user_id=%s conversation_id=%s model=%s thread_id=%s text_len=%d",
        nexus_user_id,
        conversation.id,
        model_id,
        sender.thread_id,
        len(text),
    )

    return TelegramTurnContext(
        nexus_user_id=nexus_user_id,
        conversation_id=conversation.id,
        model_id=model_id,
        thread_id=sender.thread_id,
        verbose_level=conversation.verbose_level,
    )


async def handle_new_command(
    *,
    sender: TelegramSender,
    session: AsyncSession,
) -> str:
    """Create a fresh conversation for this sender, staying in the same topic.

    ``/new`` inside a Telegram topic thread creates a new conversation
    scoped to that thread — the reply stays in the same topic. In a plain
    DM (no topics) it simply opens a blank slate, same as the web ``/new``.

    Args:
        sender: Normalized sender identity (carries ``thread_id``).
        session: Async database session.

    Returns:
        Reply string the bot should send immediately.
    """
    nexus_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if nexus_user_id is None:
        return _NEW_NOT_BOUND_MESSAGE

    from datetime import datetime  # noqa: PLC0415 — already imported by callers

    from app.models import Conversation  # noqa: PLC0415

    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=nexus_user_id,
        title="Telegram",
        origin_channel="telegram",
        telegram_thread_id=sender.thread_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(conversation)
    await session.commit()

    logger.info(
        "TELEGRAM_NEW_CONVERSATION user_id=%s conversation_id=%s thread_id=%s",
        nexus_user_id,
        conversation.id,
        sender.thread_id,
    )
    return _NEW_OK_MESSAGE


def handle_stop_command(*, was_running: bool) -> str:
    """Return the appropriate reply for a ``/stop`` command.

    Synchronous — no I/O, no async needed.  The *actual* task cancellation
    happens in ``bot.py`` which holds the ``asyncio.Task`` reference.

    .. note::
        ``_running_tasks`` in ``bot.py`` is **process-local**.  In a
        multi-worker uvicorn deployment a ``/stop`` arriving on worker A
        cannot cancel a stream running on worker B.  For single-worker
        (the current setup) this is correct; promote to Redis-backed
        cancellation before scaling horizontally.

    Args:
        was_running: ``True`` when the bot cancelled an active task for this
            chat, ``False`` when nothing was running.

    Returns:
        Reply string the bot should send immediately.
    """
    return _STOP_STOPPED_MESSAGE if was_running else _STOP_NOTHING_MESSAGE


async def handle_model_command(
    *,
    sender: TelegramSender,
    model_arg: str,
    session: AsyncSession,
) -> str:
    """Process a ``/model <id>`` command and persist the model override.

    Resolves the sender's binding, finds (or creates) their Telegram
    conversation, and updates ``Conversation.model_id`` so subsequent turns
    use the requested model.

    Args:
        sender: Normalized sender identity.
        model_arg: The whitespace-stripped text after ``/model``.  An empty
            string triggers a usage hint.
        session: Async database session.

    Returns:
        Reply string the bot should send immediately.
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

    nexus_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if nexus_user_id is None:
        return _MODEL_NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=nexus_user_id,
        session=session,
        thread_id=sender.thread_id,
    )

    # Store the canonical, fully-qualified form ("host:vendor/model"), not
    # the raw user input — keeps stored model_ids consistent regardless of
    # whether the user typed the host prefix.
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
        nexus_user_id,
        conversation.id,
        canonical_id,
    )
    return _MODEL_OK_MESSAGE.format(model_id=canonical_id)


async def handle_verbose_command(
    *,
    sender: TelegramSender,
    level_arg: str,
    session: AsyncSession,
) -> str:
    """Process a ``/verbose <0|1|2>`` command and persist the override.

    Mirrors CCT's ``/verbose`` semantics — see
    :func:`app.core.chat_aggregator.should_emit_event` for the
    filtering applied at each level.

    Args:
        sender: Normalized sender identity.
        level_arg: Whitespace-stripped text after ``/verbose``.  An
            empty string triggers the usage hint.
        session: Async database session.

    Returns:
        Reply string the bot should send immediately.
    """
    raw = level_arg.strip()
    if raw == "":
        return _VERBOSE_USAGE_MESSAGE
    try:
        level = int(raw)
    except ValueError:
        return _VERBOSE_USAGE_MESSAGE
    if level not in _VERBOSE_LABELS:
        return _VERBOSE_USAGE_MESSAGE

    nexus_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if nexus_user_id is None:
        return _VERBOSE_NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=nexus_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    updated = await update_conversation_verbose_level(
        conversation_id=conversation.id,
        verbose_level=level,
        session=session,
    )
    if not updated:
        logger.warning(
            "TELEGRAM_VERBOSE_UPDATE_FAILED conversation_id=%s level=%d",
            conversation.id,
            level,
        )
        return _VERBOSE_FAIL_MESSAGE

    logger.info(
        "TELEGRAM_VERBOSE_SET user_id=%s conversation_id=%s level=%d",
        nexus_user_id,
        conversation.id,
        level,
    )
    return _VERBOSE_OK_MESSAGE.format(level=level, label=_VERBOSE_LABELS[level])
