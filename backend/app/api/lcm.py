"""LCM debug API — inspect assembled context for a conversation turn.

This router exposes the read-only observability surface introduced in
issue #251.  It does **not** mutate state, does **not** trigger model
calls, and does **not** alter compaction; it is purely a microscope
on the existing ``lcm_context_items`` table.

Access is gated on the same per-user conversation-ownership check the
rest of the API uses (``crud.conversation.get_conversation`` returns
``Nothing`` when the conversation belongs to another user), so the
panel cannot leak history across users even if the caller fabricates
a conversation UUID.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lcm.observe import (
    LCMContextDebugResponse,
    describe_assembled_context,
)
from app.crud import conversation as crud
from app.db import User, get_async_session
from app.users import get_allowed_user

logger = logging.getLogger(__name__)


def get_lcm_router() -> APIRouter:
    """Return the LCM debug router."""
    router = APIRouter(prefix="/api/v1/lcm", tags=["lcm"])

    @router.get(
        "/conversations/{conversation_id}/context",
        response_model=LCMContextDebugResponse,
    )
    async def get_lcm_context(
        conversation_id: uuid.UUID,
        fresh_tail_count: int | None = Query(
            default=None,
            ge=0,
            le=1024,
            description=(
                "Override the configured fresh-tail window for this inspection. "
                "Does not change live assembly; only re-applies the cap to the "
                "stored items for preview."
            ),
        ),
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> LCMContextDebugResponse:
        """Return the assembled LCM context for ``conversation_id``."""
        # Returns-adoption pilot Phase 2: unwrap the ``Maybe`` at the
        # route boundary to preserve the 404 contract.
        conversation = (await crud.get_conversation(user.id, session, conversation_id)).value_or(
            None
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return await describe_assembled_context(
            session,
            conversation_id=conversation_id,
            fresh_tail_count=fresh_tail_count,
        )

    return router
