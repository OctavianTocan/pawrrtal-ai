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

import base64
import binascii
import secrets
import time
from typing import Any, Protocol, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import (
    delete_binding,
    get_binding,
    issue_link_code,
    list_bindings,
)
from app.channels.telegram.diagnostics import diagnose_telegram_state
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User, get_async_session
from app.models import ChannelBinding, Conversation
from app.schemas import (
    ChannelBindingRead,
    TelegramLinkCodeRead,
    TelegramSimulateRequest,
    TelegramSimulateResponse,
)

_TELEGRAM = "telegram"


class _TelegramWebhookService(Protocol):
    """Minimal service surface needed by the Telegram webhook endpoint."""

    async def feed_webhook_update(self, update: Any) -> None:
        """Dispatch a validated Telegram update."""


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


def _ensure_telegram_webhook_enabled(
    service: object | None,
    secret_token: str | None,
) -> None:
    """Reject requests unless Telegram webhook mode and secret validation pass."""
    if service is None or settings.telegram_mode != "webhook":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram webhook is not enabled on this deployment.",
        )
    if not settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram webhook secret is required.",
        )
    if not secrets.compare_digest(secret_token or "", settings.telegram_webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bad webhook secret.",
        )


def _ensure_telegram_simulation_enabled(service: object | None) -> None:
    """Reject synthetic updates unless the dev-only gate is explicitly enabled."""
    if not settings.telegram_simulate_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram simulation is not enabled on this deployment.",
        )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram service is not running on this deployment.",
        )


def _parse_telegram_id(value: str | None, field_name: str) -> int:
    """Parse a stored Telegram identifier into the numeric Bot API shape."""
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Telegram binding has no {field_name}.",
        )
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telegram binding has non-numeric {field_name}.",
        ) from exc


def _build_simulated_update(
    *,
    binding: ChannelBinding,
    payload: TelegramSimulateRequest,
    update_id: int,
    message_thread_id: int | None,
) -> Any:
    """Build an aiogram ``Update`` that matches Telegram's message shape."""
    from aiogram.types import Update  # noqa: PLC0415

    from app.channels.telegram._attachments import register_simulated_download  # noqa: PLC0415

    chat_id = _parse_telegram_id(binding.external_chat_id, "chat id")
    external_user_id = _parse_telegram_id(binding.external_user_id, "external user id")
    text = (payload.text or "").strip()
    has_media = payload.image is not None or payload.voice_note is not None
    message: dict[str, Any] = {
        "message_id": 0,
        "date": int(time.time()),
        "chat": {
            "id": chat_id,
            "type": "private" if chat_id == external_user_id else "supergroup",
        },
        "from": {
            "id": external_user_id,
            "is_bot": False,
            "first_name": binding.display_handle or "Pawrrtal",
        },
    }
    if text:
        message["caption" if has_media else "text"] = text
    if binding.display_handle:
        message["from"]["username"] = binding.display_handle
    if message_thread_id is not None:
        message["message_thread_id"] = message_thread_id
    if payload.image is not None:
        raw = _decode_simulated_media(payload.image.data, field_name="image.data")
        file_id = register_simulated_download(raw)
        message["photo"] = [
            {
                "file_id": file_id,
                "file_unique_id": file_id,
                "width": 1024,
                "height": 768,
                "file_size": len(raw),
            }
        ]
    if payload.voice_note is not None:
        raw = _decode_simulated_media(payload.voice_note.data, field_name="voice_note.data")
        file_id = register_simulated_download(raw)
        message["voice"] = {
            "file_id": file_id,
            "file_unique_id": file_id,
            "duration": payload.voice_note.duration_seconds,
            "mime_type": payload.voice_note.mime_type,
            "file_size": len(raw),
        }
    return Update.model_validate({"update_id": update_id, "message": message})


def _decode_simulated_media(data: str, *, field_name: str) -> bytes:
    """Decode base64 media payloads for the dev-only simulation route."""
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be valid base64.",
        ) from exc
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} cannot be empty.",
        )
    return raw


async def _latest_telegram_conversation_id(
    *,
    user_id: Any,
    message_thread_id: int | None,
    session: AsyncSession,
) -> Any | None:
    """Return the newest Telegram conversation id for this user/thread, if any."""
    stmt = (
        select(Conversation.id)
        .where(
            Conversation.user_id == user_id,
            Conversation.origin_channel == _TELEGRAM,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    if message_thread_id is None:
        stmt = stmt.where(Conversation.telegram_thread_id.is_(None))
    else:
        stmt = stmt.where(Conversation.telegram_thread_id == message_thread_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


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

    @router.get("/telegram/diagnose", include_in_schema=False)
    async def diagnose_telegram(
        request: Request,
        limit: int = 10,
        conversation_id: str | None = None,
        user: User = Depends(get_allowed_user),
    ) -> dict[str, Any]:
        """Return user-scoped Telegram runtime and persistence diagnostics."""
        bounded_limit = max(1, min(limit, 50))
        service = getattr(request.app.state, "telegram_service", None)
        return await diagnose_telegram_state(
            limit=bounded_limit,
            service=service,
            user_id=user.id,
            conversation_id=conversation_id,
        )

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
        _ensure_telegram_webhook_enabled(service, x_telegram_bot_api_secret_token)
        # Local import keeps aiogram out of the import graph for
        # deployments that don't run the channel.
        from aiogram.types import Update  # noqa: PLC0415

        body = await request.json()
        update = Update.model_validate(body)
        webhook_service = cast("_TelegramWebhookService", service)
        await webhook_service.feed_webhook_update(update)

    @router.post(
        "/telegram/simulate",
        response_model=TelegramSimulateResponse,
        include_in_schema=False,
    )
    async def simulate_telegram(
        payload: TelegramSimulateRequest,
        request: Request,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> TelegramSimulateResponse:
        """Feed a synthetic Telegram message through the live bot dispatcher.

        This route exists for local dogfood and agent-operated tests only.
        It is hidden and gated by ``TELEGRAM_SIMULATE_ENABLED`` so production
        deployments do not expose a message-injection surface by accident.
        """
        service = getattr(request.app.state, "telegram_service", None)
        _ensure_telegram_simulation_enabled(service)
        binding = await get_binding(user_id=user.id, provider=_TELEGRAM, session=session)
        if binding is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No Telegram binding exists for this user.",
            )
        update_id = int(time.time() * 1000)
        update = _build_simulated_update(
            binding=binding,
            payload=payload,
            update_id=update_id,
            message_thread_id=payload.message_thread_id,
        )
        webhook_service = cast("_TelegramWebhookService", service)
        await webhook_service.feed_webhook_update(update)
        conversation_id = await _latest_telegram_conversation_id(
            user_id=user.id,
            message_thread_id=payload.message_thread_id,
            session=session,
        )
        return TelegramSimulateResponse(
            accepted=True,
            update_id=update_id,
            chat_id=binding.external_chat_id or "",
            external_user_id=binding.external_user_id,
            conversation_id=conversation_id,
        )

    return router
