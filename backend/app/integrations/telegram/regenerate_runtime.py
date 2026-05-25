"""aiogram runtime for the regenerate-keyboard callback (#368).

The runtime answers a callback (``rgn:<conversation-id>``) by
fetching the latest user message in that conversation from the
``chat_messages`` table and posting it back into the chat so the
existing message handler picks it up — driving the standard turn
pipeline without the runtime having to duplicate any of it.

The bot's regular message handler ignores messages from itself, so
"post the user's last message verbatim" via ``bot.send_message``
won't work. Instead this runtime sends a short "🔄 Regenerating…"
notice and stores the regen state, then drives the turn directly
through the legacy ``_run_llm_turn`` import (resolved lazily to
avoid a circular import).

Ownership / authorisation: the callback verifies that
``callback.from_user.id`` matches the user who owns
``conversation_id`` before touching anything. A different Telegram
user (e.g. one who got the chat link forwarded) tapping the button
gets a stale-callback message.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, cast

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.channel import get_user_id_for_external
from app.db import async_session_maker
from app.integrations.telegram.regenerate_keyboard import (
    REGEN_CALLBACK_PREFIX,  # re-exported for bot.py one-stop import
    parse_regenerate_callback_data,
)
from app.models import ChatMessage, Conversation

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)

_TELEGRAM_PROVIDER = "telegram"
_STALE_MESSAGE = "That regenerate button is out of date. Send the message again."
_NOT_OWNER_MESSAGE = "Only the conversation owner can regenerate."
_NO_USER_MESSAGE_MESSAGE = "No previous user message to regenerate from."
_REGENERATING_NOTICE = "🔄 Regenerating…"


async def handle_regenerate_callback(*, callback: CallbackQuery) -> None:
    """Handle a ``rgn:<conversation-id>`` callback tap.

    Validates ownership, looks up the conversation's most recent
    user message, and replays it as if the user had sent it again.
    Each step that fails surfaces a callback-answer alert so the
    user knows what happened.
    """
    parsed = parse_regenerate_callback_data(callback.data)
    if parsed is None:
        await callback.answer(_STALE_MESSAGE, show_alert=True)
        return

    sender = callback.from_user
    if sender is None:
        await callback.answer(_STALE_MESSAGE, show_alert=True)
        return

    async with async_session_maker() as session:
        owner_user_id = await get_user_id_for_external(
            provider=_TELEGRAM_PROVIDER,
            external_user_id=str(sender.id),
            session=session,
        )
        if owner_user_id is None:
            await callback.answer(_STALE_MESSAGE, show_alert=True)
            return

        if not await _user_owns_conversation(
            session=session,
            conversation_id=parsed.conversation_id,
            user_id=owner_user_id,
        ):
            await callback.answer(_NOT_OWNER_MESSAGE, show_alert=True)
            return

        last_user_text = await _last_user_message_text(
            session=session,
            conversation_id=parsed.conversation_id,
        )

    if last_user_text is None:
        await callback.answer(_NO_USER_MESSAGE_MESSAGE, show_alert=True)
        return

    message = _callback_message(callback)
    if message is None:
        await callback.answer(_STALE_MESSAGE, show_alert=True)
        return

    await message.answer(_REGENERATING_NOTICE)
    await callback.answer("Regenerating…")

    # Drive the turn pipeline directly. Imported lazily to avoid a
    # ``bot ↔ regenerate_runtime`` circular import (bot.py imports
    # this module to register the callback handler; this module
    # needs bot.py's ``_run_llm_turn`` helper to re-fire the turn).
    from app.integrations.telegram.bot import (  # noqa: PLC0415 — see docstring
        _run_llm_turn,
    )
    from app.integrations.telegram.handlers import (  # noqa: PLC0415
        TelegramTurnContext,
    )

    # Synthesise a turn context from the resolved conversation. The
    # caller is the original owner so verbose settings carry over
    # verbatim from the row; ``model_id`` is left to the runner's
    # standard lookup so an empty value works.
    turn_context = TelegramTurnContext(
        pawrrtal_user_id=owner_user_id,
        conversation_id=parsed.conversation_id,
        model_id="",  # runner resolves the persisted model
        thread_id=message.message_thread_id,
        verbose_level=None,
    )

    # The message argument is the picker message — its ``answer``
    # method is what posts the assistant reply. The turn runner
    # reads ``message.text`` only when building the initial user
    # turn, so we monkey-set it to the last user text we resolved
    # from the database via a lightweight wrapper.
    await _run_llm_turn(
        message=_RegenerateMessageView(
            original=message,
            user_text=last_user_text,
        ),  # type: ignore[arg-type]
        context=turn_context,
        images=None,
        text_annotations=None,
    )


async def _user_owns_conversation(
    *,
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Check that ``user_id`` owns ``conversation_id``."""
    stmt = select(Conversation.user_id).where(Conversation.id == conversation_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row == user_id


async def _last_user_message_text(
    *,
    session: AsyncSession,
    conversation_id: uuid.UUID,
) -> str | None:
    """Return the latest user message text for ``conversation_id`` or None."""
    stmt = (
        select(ChatMessage.content)
        .where(ChatMessage.conversation_id == conversation_id)
        .where(ChatMessage.role == "user")
        .order_by(desc(ChatMessage.ordinal))
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if not row:
        return None
    return str(row)


def _callback_message(callback: CallbackQuery) -> Message | None:
    """Extract the message from a callback, returning None if unusable."""
    message = callback.message
    if message is None or not hasattr(message, "answer"):
        return None
    return cast("Message", message)


class _RegenerateMessageView:
    """Minimal :class:`Message`-shaped wrapper for the regenerated turn.

    ``_run_llm_turn`` reads only a handful of attributes off the
    aiogram message it receives (``text``, ``caption``, ``bot``,
    ``chat``, ``message_id``, ``message_thread_id``, ``answer``).
    Building a real aiogram ``Message`` object is overkill; this
    proxy carries the values we need and forwards the rest to the
    original picker message.
    """

    def __init__(self, original: Message, user_text: str) -> None:
        self._original = original
        self._user_text = user_text

    @property
    def text(self) -> str:
        """Return the last user message text for the regenerated turn."""
        return self._user_text

    @property
    def caption(self) -> None:
        """Regenerated turns never carry a caption."""
        return None

    def __getattr__(self, name: str) -> object:
        return getattr(self._original, name)


__all__ = [
    "REGEN_CALLBACK_PREFIX",
    "handle_regenerate_callback",
]
