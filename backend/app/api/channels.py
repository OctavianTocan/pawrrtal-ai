"""HTTP endpoints for the third-party messaging channel binding flow.

REBUILD STUB — bean ``pawrrtal-1irw`` (Phase 4) has the full spec.

The frontend depends on the response shapes here. Don't ship from
imagination; look at what ``frontend/lib/channels.ts`` reads.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.channels.telegram import SURFACE_TELEGRAM
from app.core.config import settings
from app.crud.channel import (
    delete_binding,
    get_binding,
    get_channel_bindings,
    issue_link_code,
)
from app.db import User, get_async_session
from app.schemas import ChannelBindingRead, TelegramLinkCodeRead
from app.users import get_allowed_user


def build_deep_link(code: str) -> str | None:
    """Compose a `https://t.me/<bot>?start=<code>` URL when configured.

    Returning ``None`` lets the frontend fall back to a plain "paste this
    code into the bot" instruction without 404-ing the user.
    """
    if not settings.telegram_bot_username:
        return None

    return f"https://t.me/{settings.telegram_bot_username}?start={quote(code)}"


def get_channels_router() -> APIRouter:
    """Build the channels router (mounted at ``/api/v1/channels``)."""
    router = APIRouter(prefix="/api/v1/channels", tags=["channels"])

    @router.get("", response_model=list[ChannelBindingRead])
    async def list_channels(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[ChannelBindingRead]:
        """List the authenticated user's channel bindings."""
        bindings = await get_channel_bindings(user.id, session)
        return [ChannelBindingRead.model_validate(binding) for binding in bindings]

    @router.post("/telegram/link", response_model=TelegramLinkCodeRead)
    async def link_telegram(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> TelegramLinkCodeRead:
        """Issue a fresh one-time Telegram link code for the authenticated user."""
        binding = await get_binding(user_id=user.id, session=session, provider=SURFACE_TELEGRAM)
        # Return an error if the binding already exists.
        if binding:
            raise HTTPException(status_code=400, detail="Binding already exists")

        # We create a new link code for the user.
        code, expires_at = await issue_link_code(
            user_id=user.id, session=session, provider=SURFACE_TELEGRAM
        )
        return TelegramLinkCodeRead(
            code=code,
            expires_at=expires_at,
            bot_username=settings.telegram_bot_username or None,
            deep_link=build_deep_link(code),
        )

    # We set 204, because it worked but we don't need to return anything.
    @router.delete("/telegram/link", response_model=None, status_code=204)
    async def unlink_telegram(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Unlink the authenticated user's Telegram channel."""
        binding_deleted = await delete_binding(
            user_id=user.id,
            session=session,
            provider=SURFACE_TELEGRAM,
        )
        # Return an error if the binding does not exist.
        if not binding_deleted:
            raise HTTPException(status_code=400, detail="Binding does not exist")

    return router
