r"""HTTP endpoints for the third-party messaging channel binding flow.

Mounted at ``/api/v1/channels``. Owned by the authenticated web user
(via the existing FastAPI-Users session cookie); the bot adapter does
not consume these routes — it talks to ``app/crud/channel.py``
directly inside the same process.

Today the only wired provider is Telegram, but the surface is shaped
to take Slack/WhatsApp/iMessage as additional `\\<provider\\>` segments
when those adapters land.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.channel import (
    delete_binding,
    issue_link_code,
    list_bindings,
)
from app.db import User, get_async_session
from app.schemas import ChannelBindingRead, TelegramLinkCodeRead
from app.users import get_allowed_user

_TELEGRAM = "telegram"


def _telegram_configured() -> bool:
    """Return True iff the deployment has a usable Telegram bot wired up.

    The bot token is the only hard requirement; username is also
    required so the frontend can render the `t.me/<bot>?start=<code>`
    deep link without guessing.
    """
    return bool(settings.telegram_bot_token and settings.telegram_bot_username)


def _build_deep_link(code: str) -> str | None:
    """Compose a `https://t.me/<bot>?start=<code>` URL when configured.

    Returning ``None`` lets the frontend fall back to a plain "paste this
    code into the bot" instruction without 404-ing the user.
    """
    if not settings.telegram_bot_username:
        return None
    return f"https://t.me/{settings.telegram_bot_username}?start={quote(code)}"


def get_channels_router() -> APIRouter:
    """Build the channels router (mounted at /api/v1/channels)."""
    router = APIRouter(prefix="/api/v1/channels", tags=["channels"])

    @router.get("", response_model=list[ChannelBindingRead])
    async def list_channels(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> list[ChannelBindingRead]:
        """List every channel the authenticated user has currently bound."""
        rows = await list_bindings(user_id=user.id, session=session)
        return [ChannelBindingRead.model_validate(row) for row in rows]

    # --- Telegram ------------------------------------------------------------

    @router.post("/telegram/link", response_model=TelegramLinkCodeRead)
    async def link_telegram(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> TelegramLinkCodeRead:
        """Issue a fresh one-time code the user can redeem in the bot.

        The plaintext code is returned exactly once. The DB only stores
        its HMAC, so even a full backup leak cannot be replayed against
        the bot. The frontend renders the code, a countdown bound to
        `expires_at`, and the deep-link button if `bot_username` is set.
        """
        if not _telegram_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Telegram channel is not configured. "
                    "Set TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME in .env."
                ),
            )
        code, expires_at = await issue_link_code(
            user_id=user.id,
            provider=_TELEGRAM,
            session=session,
        )
        return TelegramLinkCodeRead(
            code=code,
            expires_at=expires_at,
            bot_username=settings.telegram_bot_username or None,
            deep_link=_build_deep_link(code),
        )

    @router.delete("/telegram/link", status_code=status.HTTP_204_NO_CONTENT)
    async def unlink_telegram(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Drop the user's Telegram binding (idempotent on already-unbound).

        We deliberately return 204 even when there was no binding so the
        Settings UI can hit the same endpoint on every "Disconnect"
        click without first checking state.
        """
        await delete_binding(user_id=user.id, provider=_TELEGRAM, session=session)

    @router.post(
        "/telegram/webhook",
        status_code=status.HTTP_204_NO_CONTENT,
        include_in_schema=False,
    )
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> None:
        """Receive a single update from Telegram in webhook mode.

        Skipped entirely when the deployment runs in polling mode (the
        ``app.state.telegram_service`` slot will be ``None`` because the
        lifespan never wired one up). Also rejects any request whose
        ``X-Telegram-Bot-Api-Secret-Token`` header doesn't match the
        configured secret — standard Telegram webhook hardening.
        """
        service = getattr(request.app.state, "telegram_service", None)
        if service is None or settings.telegram_mode != "webhook":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Telegram webhook is not enabled on this deployment.",
            )
        if (
            settings.telegram_webhook_secret
            and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bad webhook secret.",
            )
        # Local import keeps aiogram out of the import graph for
        # deployments that don't run the channel.
        from aiogram.types import Update  # noqa: PLC0415

        body = await request.json()
        update = Update.model_validate(body)
        await service.feed_webhook_update(update)

    return router
