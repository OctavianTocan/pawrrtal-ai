"""Startup hook: repair chat turns interrupted by process death."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from app.conversations.messages_crud import fail_stale_streaming_messages
from app.infrastructure.database.legacy import async_session_maker
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

STALE_STREAMING_TURN_AGE = timedelta(seconds=30)
INTERRUPTED_TURN_MESSAGE = "Error: the assistant turn was interrupted by a service restart."


@startup_hook(order=45)
async def recover_stale_streaming_messages(app: FastAPI) -> None:
    """Fail assistant placeholders that predate this worker startup."""
    del app
    async with async_session_maker() as session:
        repaired = await fail_stale_streaming_messages(
            session,
            older_than=STALE_STREAMING_TURN_AGE,
            reason=INTERRUPTED_TURN_MESSAGE,
        )
        await session.commit()
    if repaired:
        logger.warning("STALE_STREAMING_MESSAGES_REPAIRED count=%s", repaired)
