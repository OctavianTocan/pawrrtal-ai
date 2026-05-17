"""Service helpers for the third-party messaging channel binding flow.

REBUILD STUB — bean ``pawrrtal-ei4l`` (Phase 3) has the full spec.

Two responsibilities once rebuilt: (1) the short-lived one-time code
handshake; (2) the persistent identity map plus the conversation routing
the bot reads on every inbound message.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.sql import select

from app.core.config import settings
from app.models import ChannelBinding, ChannelLinkCode


async def get_channel_bindings(user_id: uuid.UUID, session: AsyncSession) -> list[ChannelBinding]:
    """Return all channel bindings owned by the user, oldest first."""
    result = await session.execute(
        select(ChannelBinding)
        .where(ChannelBinding.user_id == user_id)
        .order_by(ChannelBinding.created_at.desc())
    )
    return list(result.scalars().all())


async def get_binding(
    user_id: uuid.UUID, session: AsyncSession, provider: str
) -> ChannelBinding | None:
    """Get a channel binding for a given user and provider. Useful to check if a binding exists for a given provider for a given user."""
    result = await session.execute(
        select(ChannelBinding)
        .where(ChannelBinding.user_id == user_id)
        .where(ChannelBinding.provider == provider)
    )
    return result.scalar_one_or_none()


async def delete_binding(user_id: uuid.UUID, session: AsyncSession, provider: str) -> bool:
    """Delete a channel binding for a given user and provider. Useful to unlink a channel for a given user."""
    binding = await get_binding(user_id=user_id, session=session, provider=provider)
    # Return False if the binding does not exist.
    if binding is None:
        return False
    # Delete the binding.
    await session.delete(binding)
    await session.commit()
    # Return True if the binding was deleted.
    return True


async def issue_link_code(
    user_id: uuid.UUID, session: AsyncSession, provider: str
) -> tuple[str, datetime]:
    """Consume a code and create the matching ``ChannelBinding``.

    Returns the newly created (or pre-existing rebinding) row when the
    code was valid, else ``None``. The caller (the bot adapter) maps
    ``None`` to a generic "code not recognized or already used"
    message — never leak which case it was.

    On a successful redemption the code row is marked used so it can
    never be replayed, even within its TTL.
    """
    # 1. Generate a plain text code.
    code = "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(8))
    # 2. Hash the code using HMAC-SHA-256.
    code_hash = hmac.new(
        settings.auth_secret.encode("utf-8"), code.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    # 3. Calculate expiry time, by taking the current time and adding 10min or a constant of some sort TODO: What is the tzinfo here?
    now: datetime = datetime.now(UTC).replace(tzinfo=None)
    expires_at: datetime = now + timedelta(minutes=10)

    # Create the link code object.
    link_code: ChannelLinkCode = ChannelLinkCode(
        code_hash=code_hash,
        user_id=user_id,
        provider=provider,
        created_at=now,
        expires_at=expires_at,
        used_at=None,
    )
    # Add the link code to the session and commit.
    # TODO: How does the session know where to put the link code?
    session.add(link_code)
    await session.commit()

    # Return the plain text code and the expiry time.
    return code, expires_at
