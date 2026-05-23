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
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.channel import (
    get_or_create_telegram_conversation_full,
    redeem_link_code,
    update_conversation_verbose_level,
)

# Re-export so ``bot.py`` imports both ``handle_plain_message`` and
# ``collect_attachments`` from the same module — keeps ``bot.py`` under
# sentrux's ``no_god_files`` fan-out budget without forcing a registry
# refactor in this PR (the long-term home is #281).
from app.integrations.telegram._attachments import (
    collect_attachments as collect_attachments,  # noqa: PLC0414
)
from app.integrations.telegram.bot_permissions import build_telegram_permission_check  # noqa: F401
from app.integrations.telegram.dev_admin import resolve_or_autolink_telegram_user
from app.integrations.telegram.model_defaults import resolve_effective_model_id
from app.integrations.telegram.sender import TelegramSender as TelegramSender  # noqa: PLC0414

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
_BIND_OK_MESSAGE = "Connected ✅ — you can now chat with Pawrrtal from here."
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

# The ``/status`` feature (formatters + handler + its copy constants)
# lives in :mod:`app.integrations.telegram.status` to keep this file
# under the file-line budget.  Re-exported below so existing callers
# (``bot.py``, tests) keep importing from ``handlers``.
from app.integrations.telegram.status import (  # noqa: E402
    _VERBOSE_LABELS,
)


@dataclass(frozen=True)
class TelegramTurnContext:
    """Resolved context for routing a Telegram message to the LLM pipeline.

    Returned by ``handle_plain_message`` when the sender has a valid binding.
    ``bot.py`` uses this to build the ``ChannelMessage`` and invoke the
    channel delivery loop.
    """

    pawrrtal_user_id: uuid.UUID
    """Pawrrtal user UUID resolved from the channel binding."""

    conversation_id: uuid.UUID
    """Stable Pawrrtal conversation for this Telegram user."""

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
        # Empty ``/start`` is the dev-admin's "hello" too. Try the
        # auto-link path so the configured Telegram ID jumps straight
        # to a connected state instead of seeing the nudge.
        pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
        return _BIND_OK_MESSAGE if pawrrtal_user_id is not None else _NOT_BOUND_MESSAGE

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
        "TELEGRAM_BIND_OK external_user_id=%s pawrrtal_user_id=%s",
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
    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
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
                    "TELEGRAM_BIND_OK_VIA_PLAIN external_user_id=%s pawrrtal_user_id=%s",
                    sender.user_id,
                    binding.user_id,
                )
                return _BIND_OK_MESSAGE
            return _BIND_BAD_CODE_MESSAGE
        return _NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    model_id = await resolve_effective_model_id(
        session=session,
        user_id=pawrrtal_user_id,
        conversation_model_id=conversation.model_id,
    )

    logger.info(
        "TELEGRAM_TURN user_id=%s conversation_id=%s model=%s thread_id=%s text_len=%d",
        pawrrtal_user_id,
        conversation.id,
        model_id,
        sender.thread_id,
        len(text),
    )

    return TelegramTurnContext(
        pawrrtal_user_id=pawrrtal_user_id,
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
    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
        return _NEW_NOT_BOUND_MESSAGE

    from app.models import Conversation  # noqa: PLC0415

    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=pawrrtal_user_id,
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
        pawrrtal_user_id,
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

    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
        return _VERBOSE_NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
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
        pawrrtal_user_id,
        conversation.id,
        level,
    )
    return _VERBOSE_OK_MESSAGE.format(level=level, label=_VERBOSE_LABELS[level])


# ``handle_status_command`` + ``_render_status_message`` are imported
# at the top of this module from ``app.integrations.telegram.status``
# and re-exported, so historical call sites keep working.
