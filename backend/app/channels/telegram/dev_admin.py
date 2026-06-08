"""Auto-link a configured Telegram user_id to the seeded dev-admin account.

When ``settings.telegram_dev_admin_id`` is set and an inbound Telegram
message arrives from that numeric user_id without an existing
``ChannelBinding`` row, this module forges the binding pointing at the
dev-admin user (whose credentials are ``ADMIN_EMAIL`` /
``ADMIN_PASSWORD``) and ensures the dev-admin workspace exists. Skips
(logging at DEBUG for sender-ID mismatch and WARNING for misconfig)
when the env var is unset (default), the admin credentials aren't
configured, or the sender's Telegram ID doesn't match.

    This avoids manually re-running ``/start <code>`` after every fresh
    branch-scoped SQLite database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import get_user_id_for_external
from app.channels.telegram.sender import TelegramSender
from app.infrastructure.config import settings
from app.infrastructure.database.legacy import User
from app.models import ChannelBinding
from app.workspace.crud import ensure_dev_admin_workspace

logger = logging.getLogger(__name__)

TELEGRAM_PROVIDER = "telegram"


async def resolve_or_autolink_telegram_user(
    *,
    session: AsyncSession,
    sender: TelegramSender,
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
        sender: The Telegram sender dataclass shared across the package.

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
    sender: TelegramSender,
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
    if dev_admin_id is None:
        return None

    external_user_id = str(sender.user_id)
    if str(dev_admin_id) != external_user_id:
        # DEBUG (not WARNING) so every non-admin sender doesn't spam
        # logs. Helps diagnose a fat-fingered TELEGRAM_DEV_ADMIN_ID
        # without paging on normal traffic.
        logger.debug(
            "TELEGRAM_DEV_ADMIN_AUTOLINK_SKIPPED reason=sender_id_mismatch "
            "configured=%s external_user_id=%s",
            dev_admin_id,
            external_user_id,
        )
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
    # workaround used by ``app.infrastructure.auth.oauth.router``'s OAuth login helper.
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

    chat_id = str(sender.chat_id)
    display_handle = sender.username or sender.full_name
    binding = ChannelBinding(
        user_id=admin_user.id,
        provider=TELEGRAM_PROVIDER,
        external_user_id=external_user_id,
        external_chat_id=chat_id,
        display_handle=display_handle,
        # Naive UTC matches the column type used throughout the codebase.
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    try:
        session.add(binding)
        # Idempotent — re-fetches the existing row when one is already present.
        await ensure_dev_admin_workspace(admin_user.id, session)
        await session.commit()
    except IntegrityError:
        # Concurrent first-contact race: another task observed an empty
        # binding lookup, raced through ``_autolink_dev_admin`` and
        # committed first, so this insert trips the
        # ``(provider, external_user_id)`` unique constraint — either
        # at autoflush (when ``ensure_dev_admin_workspace`` opens its
        # savepoint) or at the final commit. Roll back and surface the
        # winner instead of throwing — the autolink contract is "the
        # dev-admin's Telegram ID maps to *a* user", so either winner
        # satisfies the caller.
        await session.rollback()
        winner = await get_user_id_for_external(
            provider=TELEGRAM_PROVIDER,
            external_user_id=external_user_id,
            session=session,
        )
        if winner is None:
            # The IntegrityError fired without a competing row showing
            # up — something else is wrong (e.g. a different constraint
            # on the workspace insert).  Let it propagate so the failure
            # is visible.
            raise
        logger.info(
            "TELEGRAM_DEV_ADMIN_AUTOLINK_RACE external_user_id=%s pawrrtal_user_id=%s",
            external_user_id,
            winner,
        )
        return winner

    logger.info(
        "TELEGRAM_DEV_ADMIN_AUTOLINK external_user_id=%s pawrrtal_user_id=%s "
        "chat_id=%s display_handle=%s",
        external_user_id,
        admin_user.id,
        chat_id,
        display_handle,
    )
    return admin_user.id
