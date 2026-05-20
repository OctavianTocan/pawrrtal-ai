"""``/login xai`` Telegram command — kicks off the xAI OAuth device flow (#372).

The command surfaces xAI's RFC 8628 device-code flow to a Telegram user:

1. Pawrrtal calls ``request_device_code`` and posts the
   ``user_code`` + ``verification_uri`` back to the chat.
2. A background task awaits ``poll_for_token`` until the user
   authorises (or the device code expires) and writes the
   resulting access + refresh tokens to the user's default
   workspace ``.env``.
3. On success the bot follows up with a "✅ Logged in" notice.
   On failure (denied / expired / network) the user gets a
   short reason.

Why a separate module
---------------------
``bot.py`` is already at the structural ceiling. A new command
that needs its own background-task helper and message templates
belongs next to the other per-command modules
(``compact_command.py``, ``lcm_status.py``, …) so each surface
stays readable in isolation.

Future surfaces (web composer "Sign in with xAI" button) can
reuse the helper at the bottom (`drive_xai_device_flow`) — only
the messaging is Telegram-specific.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.keys import load_workspace_env, save_workspace_env
from app.crud.channel import get_user_id_for_external
from app.crud.workspace import get_default_workspace
from app.integrations.xai import (
    DeviceCodeGrant,
    DeviceCodeRequest,
    OAuthError,
    poll_for_token,
    request_device_code,
)
from app.integrations.xai.credentials import (
    ACCESS_TOKEN_KEY,
    EXPIRES_AT_KEY,
    REFRESH_TOKEN_KEY,
)

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

_PROVIDER = "telegram"

# Retain references to the background poll tasks so the event loop
# doesn't garbage-collect them mid-flight (asyncio holds only weak
# references to scheduled tasks; without the strong reference here
# the GC can finalise the task between iterations of its inner
# polling loop and the user's login silently fails). The set
# self-prunes via the done-callback below.
_pending_poll_tasks: set[asyncio.Task[None]] = set()

# Pawrrtal's chosen alias for the only positional sub-command. The
# command surface is ``/login xai`` so other providers can plug in
# without recompiling the dispatcher — but we only ship the xAI one
# right now.
LOGIN_XAI_SUBCOMMAND = "xai"

# Bind the poll deadline to xAI's 15-minute device-code lifetime.
# Slightly shorter cap here so the background task self-terminates
# before the device code does, avoiding the corner case where the
# poll succeeds against a code that the server has just expired.
_POLL_DEADLINE_SECONDS = 870.0

# Reply copy lifted out as constants so the test suite can pin
# them and so localisation lives in one place.
_NOT_BOUND_MESSAGE = "Connect your account first before running /login."
_USAGE_MESSAGE = "Usage: /login xai"
_NO_WORKSPACE_MESSAGE = "You don't have a default workspace yet — set one up in the web app first."
_NOT_CONFIGURED_MESSAGE = (
    "xAI OAuth is not enabled on this deployment (operator: set settings.xai_oauth_client_id)."
)
_REQUEST_FAILED_MESSAGE = "Couldn't reach xAI to start the login flow. Try again in a moment."
_INSTRUCTIONS_TEMPLATE = (
    "🔑 <b>Connect xAI</b>\n\n"
    "1. Open: {verification_uri}\n"
    "2. Enter the code: <code>{user_code}</code>\n\n"
    "I'll let you know when authorization completes (expires in {minutes} min)."
)
_SUCCESS_MESSAGE = "✅ Connected to xAI — your workspace can now use OAuth-backed requests."
_DENIED_MESSAGE = "❌ You denied the xAI login request."
_EXPIRED_MESSAGE = "⌛ The xAI login code expired before you authorised it. Try /login xai again."
_FAILED_MESSAGE = "❌ xAI login failed: {reason}. Try /login xai again."


class _TelegramSenderLike(Protocol):
    """Structural type for the subset of ``TelegramSender`` /login needs."""

    user_id: int
    chat_id: int


async def handle_login_command(
    *,
    sender: _TelegramSenderLike,
    bot: Bot,
    args: str,
    session: AsyncSession,
) -> str:
    """Drive the synchronous (kickoff) half of the ``/login xai`` flow.

    Returns the reply the bot sends immediately. The polling half
    runs as a background task so the bot doesn't block the Telegram
    poll loop for 15 minutes; the task posts a follow-up message
    via :meth:`Bot.send_message` when it finishes.

    Args:
        sender: Normalized sender identity (Telegram numeric user
            id + chat id used by the follow-up message).
        bot: Live aiogram ``Bot`` for the follow-up message.
        args: Whatever followed ``/login`` (trim'd). Only
            ``"xai"`` is currently recognised — anything else
            surfaces a one-liner usage hint.
        session: Async DB session for the user binding + workspace
            lookups.
    """
    if args.strip() != LOGIN_XAI_SUBCOMMAND:
        return _USAGE_MESSAGE

    pawrrtal_user_id = await get_user_id_for_external(
        provider=_PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if pawrrtal_user_id is None:
        return _NOT_BOUND_MESSAGE

    if not settings.xai_oauth_client_id:
        return _NOT_CONFIGURED_MESSAGE

    workspace = await get_default_workspace(pawrrtal_user_id, session)
    if workspace is None:
        return _NO_WORKSPACE_MESSAGE

    try:
        device_request = await request_device_code(client_id=settings.xai_oauth_client_id)
    except OAuthError as exc:
        logger.warning(
            "XAI_LOGIN_REQUEST_FAILED user_id=%s code=%s",
            pawrrtal_user_id,
            exc.code,
        )
        return _REQUEST_FAILED_MESSAGE

    # Background task: own the polling loop + the on-success env
    # write. We pin a name on the task so it shows up in repr/log
    # output and so the test suite can find it; we also pin a
    # strong reference in ``_pending_poll_tasks`` so asyncio's GC
    # doesn't finalise the task between polling iterations.
    poll_task = asyncio.create_task(
        _drive_poll_and_persist(
            bot=bot,
            chat_id=sender.chat_id,
            workspace_root=Path(workspace.path),
            device_request=device_request,
        ),
        name=f"xai-login-poll-{pawrrtal_user_id}",
    )
    _pending_poll_tasks.add(poll_task)
    poll_task.add_done_callback(_pending_poll_tasks.discard)

    minutes = max(1, device_request.expires_in // 60)
    return _INSTRUCTIONS_TEMPLATE.format(
        verification_uri=device_request.verification_uri,
        user_code=device_request.user_code,
        minutes=minutes,
    )


async def _drive_poll_and_persist(
    *,
    bot: Bot,
    chat_id: int,
    workspace_root: Path,
    device_request: DeviceCodeRequest,
) -> None:
    """Poll until xAI grants a token, then write it to the workspace env."""
    try:
        grant = await poll_for_token(
            client_id=settings.xai_oauth_client_id,
            device_code=device_request.device_code,
            interval=device_request.interval,
            deadline_seconds=_POLL_DEADLINE_SECONDS,
        )
    except OAuthError as exc:
        reply = _format_failure(exc.code)
        logger.warning(
            "XAI_LOGIN_POLL_FAILED workspace=%s code=%s",
            workspace_root,
            exc.code,
        )
        await _safe_followup(bot, chat_id, reply)
        return

    persist_xai_oauth_grant(workspace_root, grant)
    await _safe_followup(bot, chat_id, _SUCCESS_MESSAGE)


def persist_xai_oauth_grant(workspace_root: Path, grant: DeviceCodeGrant) -> None:
    """Write the OAuth grant to the workspace ``.env`` in the canonical key shape.

    The keys mirror what :func:`resolve_xai_credentials` reads back.
    Exposed as a public helper so the future web-composer flow can
    persist the same shape without re-implementing the key names.
    """
    env = load_workspace_env(workspace_root)
    env[ACCESS_TOKEN_KEY] = grant.access_token
    if grant.refresh_token is not None:
        env[REFRESH_TOKEN_KEY] = grant.refresh_token
    expires_at = datetime.now(UTC) + timedelta(seconds=grant.expires_in)
    env[EXPIRES_AT_KEY] = expires_at.isoformat()
    save_workspace_env(workspace_root, env)


def _format_failure(code: str | None) -> str:
    """Map an :class:`OAuthError` code to user-facing copy."""
    if code == "access_denied":
        return _DENIED_MESSAGE
    if code == "expired_token":
        return _EXPIRED_MESSAGE
    return _FAILED_MESSAGE.format(reason=code or "unknown")


async def _safe_followup(bot: Bot, chat_id: int, text: str) -> None:
    """Post the closing message; swallow Telegram errors so the task can't crash the loop."""
    # ``aiogram``'s exception classes are imported lazily here for the
    # same reason :mod:`telegram_delivery` does: aiogram is optional
    # in non-Telegram pytest runs.
    from aiogram.exceptions import (  # noqa: PLC0415
        TelegramAPIError,
        TelegramNetworkError,
    )

    with contextlib.suppress(TelegramAPIError, TelegramNetworkError):
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


# Re-exported via __all__ so the import surface stays small.
__all__ = [
    "LOGIN_XAI_SUBCOMMAND",
    "handle_login_command",
    "persist_xai_oauth_grant",
]
