"""Conversation export API.

Single endpoint returning a downloadable conversation snapshot in
Markdown / HTML / JSON.  Per-user scoped via ``get_allowed_user`` so
a user can only export their own conversations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.crud import get_conversation
from app.conversations.exports import render_html, render_json, render_markdown
from app.conversations.messages_crud import get_messages_for_conversation
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session

logger = logging.getLogger(__name__)

ExportFormat = Literal["md", "html", "json"]

# Hard cap on the messages slice per export — same as the chat
# rehydration endpoint to keep download size bounded.
MAX_MESSAGES_PER_EXPORT = 1000

# MIME + extension table per format. Centralised so adding a new
# format is one row + one renderer.
_FORMAT_MIME: dict[ExportFormat, tuple[str, str]] = {
    "md": ("text/markdown; charset=utf-8", "md"),
    "html": ("text/html; charset=utf-8", "html"),
    "json": ("application/json", "json"),
}


def get_exports_router() -> APIRouter:
    """Build the conversation export router."""
    router = APIRouter(prefix="/api/v1/conversations", tags=["exports"])

    @router.get("/{conversation_id}/export")
    async def export_conversation(
        conversation_id: uuid.UUID,
        format: ExportFormat = Query(default="md"),  # noqa: A002 — matches HTTP convention
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> Response:
        """Return a downloadable snapshot of the conversation in the requested format.

        Per-user scoped — a user can only export their own
        conversations; anything else returns 404 (not 403, so we
        don't leak existence).
        """
        # Returns-adoption pilot Phase 2: unwrap the ``Maybe`` at the
        # Boundary check: 404 when the conversation isn't visible to this user.
        conversation = await get_conversation(
            user_id=user.id,
            session=session,
            conversation_id=conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = await get_messages_for_conversation(
            session=session,
            conversation_id=conversation_id,
            limit=MAX_MESSAGES_PER_EXPORT,
        )

        if format == "md":
            body = render_markdown(conversation=conversation, messages=messages)
        elif format == "html":
            body = render_html(conversation=conversation, messages=messages)
        else:
            body = render_json(conversation=conversation, messages=messages)

        media_type, extension = _FORMAT_MIME[format]
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"conversation_{conversation_id.hex[:8]}_{timestamp}.{extension}"

        logger.info(
            "EXPORT user_id=%s conversation_id=%s format=%s message_count=%d bytes=%d",
            user.id,
            conversation_id,
            format,
            len(messages),
            len(body.encode()),
        )
        return Response(
            content=body,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return router
