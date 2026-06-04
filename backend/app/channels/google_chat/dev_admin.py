"""Auto-link a configured Google Chat sender to the seeded dev-admin account.

Mirror of :mod:`app.channels.telegram.dev_admin`. When
``settings.google_chat_dev_admin_id`` is set and an inbound Chat message
arrives from that sender resource name (e.g. ``"users/1234567890"``)
without an existing ``ChannelBinding`` row, this module forges the
binding pointing at the dev-admin user (``ADMIN_EMAIL`` /
``ADMIN_PASSWORD``) and ensures the dev-admin workspace exists. Skips
(DEBUG for sender mismatch, WARNING for misconfig) when the env var is
unset (default), the admin credentials aren't configured, or the
sender's id doesn't match.

This is the single-user dogfood path: one Google account maps to the
dev-admin, no link-code flow.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import get_user_id_for_external
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User
from app.models import ChannelBinding
from app.workspace.crud import ensure_dev_admin_workspace

from .settings import google_chat_settings

logger = logging.getLogger(__name__)

GOOGLE_CHAT_PROVIDER = "google_chat"


async def resolve_or_autolink_google_chat_user(
    *,
    session: AsyncSession,
    external_user_id: str,
    space_name: str,
    display: str | None,
) -> uuid.UUID | None:
    """Resolve a Chat sender to its Pawrrtal user UUID.

    Auto-links the dev-admin Google identity on first contact when no
    binding exists. Returns the bound user UUID when a ``ChannelBinding``
    exists, or when the sender matches ``settings.google_chat_dev_admin_id``
    and the auto-link succeeds. Returns ``None`` for senders that aren't
    bound and aren't the configured dev-admin.

    Args:
        session: Async database session.
        external_user_id: Chat sender resource name (``users/{id}``).
        space_name: ``spaces/{id}`` the message came from (stored as the
            binding's default chat target).
        display: Sender display name captured at bind time, if any.

    Returns:
        The Pawrrtal user UUID, or ``None`` if no binding can be
        established.
    """
    existing = await get_user_id_for_external(
        provider=GOOGLE_CHAT_PROVIDER,
        external_user_id=external_user_id,
        session=session,
    )
    if existing is not None:
        return existing

    return await _autolink_dev_admin(
        session=session,
        external_user_id=external_user_id,
        space_name=space_name,
        display=display,
    )


async def _autolink_dev_admin(
    *,
    session: AsyncSession,
    external_user_id: str,
    space_name: str,
    display: str | None,
) -> uuid.UUID | None:
    """Forge a ``ChannelBinding`` for the dev-admin on sender-id match.

    Fires only when the sender matches ``settings.google_chat_dev_admin_id``.
    Also ensures the dev-admin workspace exists so the first Chat turn
    doesn't trip the post-onboarding gate. Returns ``None`` when any
    precondition is missing.
    """
    dev_admin_id = google_chat_settings.google_chat_dev_admin_id
    if not dev_admin_id:
        return None

    if dev_admin_id != external_user_id:
        # DEBUG (not WARNING) so every non-admin sender doesn't spam logs.
        logger.debug(
            "GOOGLE_CHAT_DEV_ADMIN_AUTOLINK_SKIPPED reason=sender_id_mismatch "
            "configured=%s external_user_id=%s",
            dev_admin_id,
            external_user_id,
        )
        return None

    admin_email = settings.admin_email
    if not admin_email:
        logger.warning(
            "GOOGLE_CHAT_DEV_ADMIN_AUTOLINK_SKIPPED reason=admin_email_unset external_user_id=%s",
            external_user_id,
        )
        return None

    # Reach the column via ``__table__.c`` so mypy sees a real
    # ``ColumnElement[bool]`` (the fastapi-users base class declares
    # ``email: str`` which shadows the SQLAlchemy descriptor). Same
    # workaround the Telegram autolink uses.
    stmt = select(User).where(User.__table__.c.email == admin_email)
    admin_user = (await session.execute(stmt)).scalar_one_or_none()
    if admin_user is None:
        logger.warning(
            "GOOGLE_CHAT_DEV_ADMIN_AUTOLINK_SKIPPED reason=admin_user_not_found "
            "email=%s external_user_id=%s",
            admin_email,
            external_user_id,
        )
        return None

    binding = ChannelBinding(
        user_id=admin_user.id,
        provider=GOOGLE_CHAT_PROVIDER,
        external_user_id=external_user_id,
        external_chat_id=space_name,
        display_handle=display,
        # Naive UTC matches the column type used throughout the codebase.
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    try:
        session.add(binding)
        # Idempotent — re-fetches the existing row when one is already present.
        await ensure_dev_admin_workspace(admin_user.id, session)
        await session.commit()
    except IntegrityError:
        # Concurrent first-contact race: another task committed the
        # binding first, tripping the (provider, external_user_id) unique
        # constraint. Roll back and surface the winner — the autolink
        # contract is "this sender maps to *a* user", so either winner
        # satisfies the caller.
        await session.rollback()
        winner = await get_user_id_for_external(
            provider=GOOGLE_CHAT_PROVIDER,
            external_user_id=external_user_id,
            session=session,
        )
        if winner is None:
            raise
        logger.info(
            "GOOGLE_CHAT_DEV_ADMIN_AUTOLINK_RACE external_user_id=%s pawrrtal_user_id=%s",
            external_user_id,
            winner,
        )
        return winner

    logger.info(
        "GOOGLE_CHAT_DEV_ADMIN_AUTOLINK external_user_id=%s pawrrtal_user_id=%s space=%s",
        external_user_id,
        admin_user.id,
        space_name,
    )
    return admin_user.id
