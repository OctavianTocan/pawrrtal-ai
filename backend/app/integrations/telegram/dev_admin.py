"""Auto-link a configured Telegram user_id to the seeded dev-admin account.

When ``settings.telegram_dev_admin_id`` is set and an inbound Telegram
message arrives from that numeric user_id without an existing
``ChannelBinding`` row, this module forges the binding pointing at the
dev-admin user (whose credentials are ``ADMIN_EMAIL`` /
``ADMIN_PASSWORD``) and ensures the dev-admin workspace exists. Skips
silently when the env var is unset (default), the admin credentials
aren't configured, or the sender's Telegram ID doesn't match.

Pairs with the branch-scoped SQLite filename (PR #363): switching git
branches now spins up a fresh DB and an empty bindings table, which
previously meant manually re-running ``/start <code>`` after every
checkout. With this auto-link the dev-admin's Telegram identity is
re-bound on first contact in each new database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.channel import get_user_id_for_external
from app.crud.workspace import ensure_dev_admin_workspace
from app.db import User
from app.models import ChannelBinding

logger = logging.getLogger(__name__)

TELEGRAM_PROVIDER = "telegram"


class TelegramSenderLike(Protocol):
    """Structural type for a Telegram sender — matches ``handlers.TelegramSender``.

    Declared here so this module never imports from ``handlers`` (which
    imports back, creating a cycle). Properties (not bare class
    annotations) so a ``frozen=True`` dataclass — whose fields pyright
    treats as read-only — satisfies the contract.
    """

    @property
    def user_id(self) -> int:
        """Telegram numeric user id."""
        ...

    @property
    def chat_id(self) -> int:
        """Telegram chat id where bot replies should be pushed."""
        ...

    @property
    def username(self) -> str | None:
        """``@handle`` (no leading ``@``) when the user has one set."""
        ...

    @property
    def full_name(self) -> str | None:
        """Human-readable display name captured by aiogram."""
        ...


async def resolve_or_autolink_telegram_user(
    *,
    session: AsyncSession,
    sender: TelegramSenderLike,
) -> uuid.UUID | None:
    """Resolve a Telegram sender to its Pawrrtal user UUID.

    Auto-links the dev-admin Telegram ID on first contact when no
    binding exists. Returns the bound user UUID when a
    ``ChannelBinding`` exists, or when the sender matches
    ``settings.telegram_dev_admin_id`` and the auto-link succeeds.
    Returns ``None`` for senders that should be routed through the
    standard onboarding nudge.

    Args:
        session: Async database session.
        sender: Object exposing the Telegram sender fields
            (``user_id``, ``chat_id``, ``username``, ``full_name``).

    Returns:
        The Pawrrtal user UUID, or ``None`` if no binding can be
        established.
    """
    external_user_id = str(sender.user_id)
    existing = await get_user_id_for_external(
        provider=TELEGRAM_PROVIDER,
        external_user_id=external_user_id,
        session=session,
    )
    if existing is not None:
        return existing

    return await _autolink_dev_admin(session=session, sender=sender)


async def _autolink_dev_admin(
    *,
    session: AsyncSession,
    sender: TelegramSenderLike,
) -> uuid.UUID | None:
    """Forge a ``ChannelBinding`` for the dev-admin on Telegram ID match.

    Fires only when the sender's Telegram ID matches
    ``settings.telegram_dev_admin_id``. Also ensures the dev-admin
    workspace exists so the first Telegram turn doesn't trip the
    post-onboarding gate. Returns ``None`` when any precondition is
    missing — the caller should fall through to the standard
    onboarding nudge.
    """
    dev_admin_id = settings.telegram_dev_admin_id
    external_user_id = str(sender.user_id)
    if dev_admin_id is None or str(dev_admin_id) != external_user_id:
        return None

    admin_email = settings.admin_email
    if not admin_email:
        logger.warning(
            "TELEGRAM_DEV_ADMIN_AUTOLINK_SKIPPED reason=admin_email_unset external_user_id=%s",
            external_user_id,
        )
        return None

    # Reach the column via ``__table__.c`` so mypy sees a real
    # ``ColumnElement[bool]`` (the fastapi-users base class declares
    # ``email: str`` which shadows the SQLAlchemy descriptor). Same
    # workaround documented in :func:`app.api.oauth._login_or_create_user`.
    stmt = select(User).where(User.__table__.c.email == admin_email)
    admin_user = (await session.execute(stmt)).scalar_one_or_none()
    if admin_user is None:
        logger.warning(
            "TELEGRAM_DEV_ADMIN_AUTOLINK_SKIPPED reason=admin_user_not_found "
            "email=%s external_user_id=%s",
            admin_email,
            external_user_id,
        )
        return None

    binding = ChannelBinding(
        user_id=admin_user.id,
        provider=TELEGRAM_PROVIDER,
        external_user_id=external_user_id,
        external_chat_id=str(sender.chat_id),
        display_handle=sender.username or sender.full_name,
        # Naive UTC matches the column type used throughout the codebase.
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(binding)
    # Idempotent — re-fetches the existing row when one is already present.
    await ensure_dev_admin_workspace(admin_user.id, session)
    await session.commit()

    logger.info(
        "TELEGRAM_DEV_ADMIN_AUTOLINK external_user_id=%s nexus_user_id=%s",
        external_user_id,
        admin_user.id,
    )
    return admin_user.id
