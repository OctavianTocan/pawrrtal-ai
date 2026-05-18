"""Inbound message handlers for the Telegram channel adapter.

REBUILD STUB — bean ``pawrrtal-w8xp`` (Phase 8) has the full spec.

The design rule: **no aiogram imports in this file**. Handlers take a
plain dataclass and a session, return either a reply string or a turn
context. That's what makes the tests easy.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio.session import AsyncSession

from app.crud.channel import redeem_link_code
from app.models import ChannelBinding

# Logger for this module.
logger = logging.getLogger(__name__)

_NOT_BOUND_MESSAGE = (
    "Hey 👋 I don't recognize this Telegram account yet.\n\n"
    "To connect it, log in on the web app, open Settings → Channels, "
    "click 'Connect Telegram', and either tap the deep link or send me "
    "the code you'll see there."
)
_BIND_BAD_CODE_MESSAGE = (
    "That code didn't work. It may have expired (codes live for 10 minutes) "
    "or already been used. Generate a fresh one from Settings → Channels."
)
_BIND_OK_MESSAGE = "Connected ✅ — you can now chat with Pawrrtal from here."


@dataclass(frozen=True)
class TelegramSender:
    """Stable subset of an aiogram ``Message.from_user`` we need.

    Modeled as a plain dataclass so handler tests don't have to import aiogram
    or build a fake bot.
    """

    # The user's unique ID on Telegram.
    user_id: int
    # The chat's unique ID on Telegram.
    chat_id: int

    # The user's username on Telegram. TODO: Why do we need this? Is it not enough with the user_id?
    username: str | None

    # The thread's unique ID on Telegram.
    thread_id: int | None = None


@dataclass(frozen=True)
class TelegramTurnContext:
    """Resolved context for routing a Telegram message to the LLM pipeline.

    Returned by ``handle_plain_message`` when the sender has a valid binding.
    ``bot.py`` uses this to build the ``ChannelMessage`` and invoke the
    channel delivery loop.
    """

    # The Pawrrtal user ID resolved from the channel binding.
    pawrrtal_user_id: uuid.UUID
    conversation_id: uuid.UUID


async def handle_start_command(
    *,
    sender: TelegramSender,
    payload: str | None,
    session: AsyncSession,
) -> str:
    """Handle the /start command."""
    code: str = (payload or "").strip()
    if not code:
        return _NOT_BOUND_MESSAGE

    # Redeem the link code.
    binding: ChannelBinding | None = await redeem_link_code()

    # If we didn't succeed, return the bad code message. The user did not input a valid code.
    if binding is None:
        return _BIND_BAD_CODE_MESSAGE

    logger.info(
        "TELEGRAM_BIND_OK external_user_id=%s pawrrtal_user_id=%s",
        sender.user_id,
        binding.user_id,
    )

    return _BIND_OK_MESSAGE
