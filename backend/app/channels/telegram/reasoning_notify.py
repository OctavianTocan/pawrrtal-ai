"""Telegram side-effect wrappers around the reasoning-effort resolver.

Pulled out of ``bot.py`` and ``handlers.py`` so those modules' fan-out
stays under sentrux's ``no_god_files`` budget. The public helpers:

* :func:`normalize_reasoning_and_notify` — backstop for the
  Telegram turn entry point. Reads the stored override, normalizes
  it against the current model, and pushes a Telegram notice when
  the resolver adapted or cleared the value.
* :func:`maybe_append_model_switch_notice` — single-call helper
  used by the ``/model`` command path. Runs the resolver against
  the freshly-chosen model and either returns the original reply
  or returns the reply with a blank line plus a notice appended,
  when the user-visible level changed.

Both wrap the pure resolver in
:mod:`app.providers.reasoning`; the resolver itself stays
side-effect-free and DB-agnostic.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.channels.crud import normalize_conversation_reasoning_effort
from app.infrastructure.database.legacy import async_session_maker
from app.providers.reasoning import format_adaptation_notice

if TYPE_CHECKING:
    from aiogram.types import Message
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.providers.base import ReasoningEffort


async def normalize_reasoning_and_notify(
    *,
    message: Message,
    conversation_id: uuid.UUID,
    model_id: str | None,
) -> ReasoningEffort | None:
    """Run the backstop + push a Telegram notice when the resolver changed something.

    Returns the effective reasoning effort to pass into
    ``ChatTurnInput.reasoning_effort``. ``None`` means "let the
    provider pick its default" — either no override is stored, or
    the model doesn't honour reasoning levels at all.

    The notice (when emitted) goes via ``message.answer`` so it
    lands as a separate Telegram message before the agent turn
    starts. Silent adapts/clears would be a footgun (``/thinking`` is
    an explicit user preference), so we always surface the change.

    Args:
        message: The inbound aiogram message used to anchor the
            notice reply.
        conversation_id: The Pawrrtal conversation whose reasoning
            override should be normalized.
        model_id: The model id about to be used for this turn — pass
            it explicitly so the resolver sees the current model
            even when the row's stored model_id is stale.
    """
    async with async_session_maker() as session:
        resolution, previous_effort = await normalize_conversation_reasoning_effort(
            conversation_id=conversation_id,
            session=session,
            model_id_override=model_id,
        )

    if resolution is None:
        return None

    notice = format_adaptation_notice(resolution, previous_effort=previous_effort)
    if notice is not None:
        # No reply-parameters quote here on purpose: the notice is
        # informational, not a quoted reply to the user's message.
        await message.answer(notice)
    return resolution.effective


async def maybe_append_model_switch_notice(
    *,
    base_reply: str,
    conversation_id: uuid.UUID,
    new_model_id: str,
    session: AsyncSession,
) -> str:
    """Re-validate the stored override against a freshly-chosen model.

    Called by the Telegram ``/model`` command (and indirectly by the
    model picker, which dispatches through the same handler). The
    caller has just persisted ``new_model_id`` on the conversation;
    we run the resolver to:

    * adapt the stored effort to whatever the new model honours, or
    * clear it when the new model doesn't accept reasoning levels.

    When the resolver did something user-visible (``adapted`` or
    ``cleared``), we append a one-line notice to the reply so the
    operator sees the change. Otherwise the base reply is returned
    untouched.

    ``session`` is passed in so we share the caller's transaction —
    the model_id change and the reasoning-effort normalization land
    atomically as one commit. The previous effort comes back from
    :func:`normalize_conversation_reasoning_effort` directly so
    the caller doesn't need a separate read.
    """
    resolution, previous_effort = await normalize_conversation_reasoning_effort(
        conversation_id=conversation_id,
        session=session,
        model_id_override=new_model_id,
    )
    if resolution is None:
        return base_reply
    notice = format_adaptation_notice(resolution, previous_effort=previous_effort)
    return f"{base_reply}\n\n{notice}" if notice else base_reply
