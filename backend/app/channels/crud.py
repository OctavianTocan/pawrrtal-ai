"""Service helpers for the third-party messaging channel binding flow.

Two responsibilities live here:

1. Issuing + redeeming the short-lived one-time codes that prove a
   user logged into the web app actually owns a given Telegram chat
   (or, in the future, Slack workspace, WhatsApp number, ...).
2. Reading + writing the persistent `channel_bindings` rows that the
   inbound message path uses to resolve a third-party identity into
   a Pawrrtal user.

Codes are stored hashed; the user-facing plaintext is only ever
returned from `issue_link_code` and never persisted as-is. All lookups
go through `_hash_code` so a stolen DB cannot be replayed against the
bot.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import settings
from app.models import ChannelBinding, ChannelLinkCode

if TYPE_CHECKING:
    from app.models import Conversation

# Code alphabet excludes look-alikes (0/O, 1/I/L) so support tickets
# don't end up arguing over what the user actually typed. Eight chars
# from a 32-char alphabet is ~40 bits of entropy, plenty for a code
# that lives 10 minutes and is single-use.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8

# How long a freshly issued code stays redeemable. Short on purpose so
# stolen codes age out before they're useful, but long enough that a
# user who got distracted mid-flow can still finish without restarting.
LINK_CODE_TTL = timedelta(minutes=10)


def _utcnow() -> datetime:
    """Return a naive UTC ``datetime`` matching the column type used elsewhere."""
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_code(code: str) -> str:
    """HMAC-SHA-256 the user-facing code with the app's auth secret.

    Using HMAC (vs a bare SHA) means an attacker who exfiltrates the
    `channel_link_codes` table still needs the server secret to grind
    candidate codes against the rows. Stored as hex so the column can
    be a fixed-length text PK in both Postgres and SQLite.
    """
    key = (settings.auth_secret or "").encode("utf-8")
    return hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()


def _generate_code() -> str:
    """Allocate a fresh user-facing link code from the look-alike-free alphabet."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


async def issue_link_code(
    *,
    user_id: uuid.UUID,
    provider: str,
    session: AsyncSession,
) -> tuple[str, datetime]:
    """Generate, persist, and return a one-time channel link code.

    Returns the plaintext code (which is what the user sees) and the
    UTC expiry timestamp the frontend renders as a countdown. The
    plaintext is never stored — only its HMAC hash hits the DB.
    """
    code = _generate_code()
    code_hash = _hash_code(code)
    now = _utcnow()
    expires_at = now + LINK_CODE_TTL

    row = ChannelLinkCode(
        code_hash=code_hash,
        user_id=user_id,
        provider=provider,
        created_at=now,
        expires_at=expires_at,
        used_at=None,
    )
    session.add(row)
    await session.commit()
    return code, expires_at


async def redeem_link_code(
    *,
    code: str,
    provider: str,
    external_user_id: str,
    external_chat_id: str | None,
    display_handle: str | None,
    session: AsyncSession,
) -> ChannelBinding | None:
    """Consume a code and create the matching ``ChannelBinding``.

    Returns the newly created (or pre-existing rebinding) row when the
    code was valid, else ``None``. The caller (the bot adapter) maps
    ``None`` to a generic "code not recognized or already used"
    message — never leak which case it was.

    On a successful redemption the code row is marked used so it can
    never be replayed, even within its TTL.
    """
    code_hash = _hash_code(code)
    now = _utcnow()

    code_row = await session.get(ChannelLinkCode, code_hash)
    if code_row is None:
        return None
    if code_row.provider != provider:
        # Code was issued for a different channel; treat as invalid so
        # the bot doesn't reveal the existence of a Slack code to a
        # Telegram user, etc.
        return None
    if code_row.used_at is not None or code_row.expires_at <= now:
        return None

    # If this provider/external_user_id pair was already bound (e.g.
    # the user is rebinding after having unbound), update it in place
    # so we never end up with two rows fighting for the same identity.
    existing_stmt = select(ChannelBinding).where(
        ChannelBinding.provider == provider,
        ChannelBinding.external_user_id == external_user_id,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()

    if existing is not None:
        existing.user_id = code_row.user_id
        existing.external_chat_id = external_chat_id
        existing.display_handle = display_handle
        binding = existing
    else:
        binding = ChannelBinding(
            user_id=code_row.user_id,
            provider=provider,
            external_user_id=external_user_id,
            external_chat_id=external_chat_id,
            display_handle=display_handle,
            created_at=now,
        )
        session.add(binding)

    code_row.used_at = now
    await session.commit()
    await session.refresh(binding)
    return binding


async def list_bindings(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> list[ChannelBinding]:
    """Return all channel bindings owned by ``user_id``, newest first."""
    stmt = (
        select(ChannelBinding)
        .where(ChannelBinding.user_id == user_id)
        .order_by(ChannelBinding.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_binding(
    *,
    user_id: uuid.UUID,
    provider: str,
    session: AsyncSession,
) -> ChannelBinding | None:
    """Return the user's binding for ``provider`` if one exists, else ``None``.

    Useful as an exists-check before issuing a fresh link code or for
    surfacing the connected state in the Settings UI.
    """
    stmt = select(ChannelBinding).where(
        ChannelBinding.user_id == user_id,
        ChannelBinding.provider == provider,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_binding(
    *,
    user_id: uuid.UUID,
    provider: str,
    session: AsyncSession,
) -> bool:
    """Remove the user's binding for ``provider`` if one exists.

    Returns ``True`` when a row was deleted, ``False`` when the user
    had no binding for that provider. The Settings UI calls the
    matching route unconditionally — translating the ``False`` to a
    204 keeps the click idempotent.
    """
    row = await get_binding(user_id=user_id, provider=provider, session=session)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_user_id_for_external(
    *,
    provider: str,
    external_user_id: str,
    session: AsyncSession,
) -> uuid.UUID | None:
    """Resolve a third-party identity to its bound Pawrrtal ``user_id``.

    Returns ``None`` when no binding exists; the inbound bot path uses
    that signal to send the onboarding nudge ("send me your code or
    visit /settings/channels to link this account") rather than try
    to chat anonymously.
    """
    stmt = select(ChannelBinding.user_id).where(
        ChannelBinding.provider == provider,
        ChannelBinding.external_user_id == external_user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_telegram_conversation(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> uuid.UUID:
    """Return a stable Telegram conversation UUID for *user_id*.

    Finds the most-recent conversation whose title starts with ``"Telegram"``
    and was created for this user, or creates a fresh one if none exists.
    Keeping a persistent conversation means message history survives across
    bot restarts, giving the LLM access to the thread's prior turns just as
    the web UI would.

    Args:
        user_id: Pawrrtal user who owns the conversation.
        session: Async database session.

    Returns:
        UUID of the resolved (or newly created) ``Conversation`` row.
    """
    conv = await _get_or_create_telegram_conv_row(user_id=user_id, session=session)
    return conv.id


async def get_or_create_telegram_conversation_full(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    thread_id: int | None = None,
) -> Conversation:
    """Like :func:`get_or_create_telegram_conversation` but returns the full row.

    The extra fields (particularly ``model_id``) let the bot honour per-session
    model overrides set by ``/model`` without a second round-trip.

    Args:
        user_id: Pawrrtal user who owns the conversation.
        session: Async database session.
        thread_id: Telegram topic thread ID (Bot API 9.3+).  When set,
            the query scopes to conversations with a matching
            ``telegram_thread_id``; otherwise it falls back to the
            pre-topic ``title.like("Telegram%")`` lookup for plain DMs.

    Returns:
        The resolved or newly created ``Conversation`` ORM row.
    """
    return await _get_or_create_telegram_conv_row(
        user_id=user_id, session=session, thread_id=thread_id
    )


async def _get_or_create_telegram_conv_row(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    thread_id: int | None = None,
) -> Conversation:
    """Internal helper: find or create the Telegram conversation row.

    Routing branches:
    - ``thread_id`` set → query by ``(user_id, telegram_thread_id)``; each
      Telegram topic gets its own independent conversation.
    - ``thread_id`` None → pre-topic DM mode; find the most recently updated
      conversation whose title starts with "Telegram" and has no thread ID.
    """
    from app.models import Conversation  # noqa: PLC0415

    if thread_id is not None:
        # Topic mode — one conversation per thread.
        stmt = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.telegram_thread_id == thread_id,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
    else:
        # Legacy DM mode — reuse the existing Telegram conversation.
        stmt = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.origin_channel == "telegram",
                Conversation.telegram_thread_id.is_(None),
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )

    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    from datetime import datetime  # noqa: PLC0415

    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Telegram",
        origin_channel="telegram",
        telegram_thread_id=thread_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation
