"""Dreaming trigger that fires after each turn's finalization (#341).

Lives next to :mod:`turn_runner` instead of inside it so the runner
stays under the 500-line budget. Pure side-effect helper: opens a
session, calls the throttled scheduler, swallows errors.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.channels.turn_runner import ChatTurnInput

logger = logging.getLogger(__name__)

SessionOpener = Callable[["ChatTurnInput"], AbstractAsyncContextManager[AsyncSession]]
"""Shape of the runner's session context manager.

Passed in so the helper doesn't import from
:mod:`app.channels.turn_runner` and create a circular dependency
— the runner already imports from this module.
"""


async def trigger_dreaming(
    turn_input: ChatTurnInput,
    open_session: SessionOpener,
) -> None:
    """Schedule a throttled dreaming pass for the just-finished turn.

    Opens its own session via ``open_session`` and swallows any
    errors so a dreaming-trigger failure can't break the user's
    turn completion. The actual LLM call + memory writes happen on
    the background task the throttled scheduler spawns.
    """
    # Lazy import so the dreaming package isn't a startup dependency
    # for deployments running with ``dreaming_enabled=False``.
    from app.core.dreaming import schedule_session_end_dream_if_idle  # noqa: PLC0415

    try:
        async with open_session(turn_input) as session:
            await schedule_session_end_dream_if_idle(
                session,
                user_id=turn_input.user_id,
                conversation_id=turn_input.conversation_id,
            )
    except Exception:
        logger.exception(
            "DREAMING_TRIGGER_ERR conversation_id=%s",
            turn_input.conversation_id,
        )


__all__ = [
    "SessionOpener",
    "trigger_dreaming",
]
