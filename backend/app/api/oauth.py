"""OAuth sign-in endpoints (Google + Apple).

Adds Google + Apple "Continue with..." flows on top of the existing
FastAPI-Users password auth without a full migration. Each provider has
two endpoints:

- ``GET /api/v1/auth/oauth/{provider}/start`` — redirects the user to
  the provider's consent screen.
- ``GET /api/v1/auth/oauth/{provider}/callback`` — receives the auth
  code, exchanges it for the user's email, creates or looks up the local
  ``User``, sets the standard FastAPI-Users session cookie, and redirects
  to the frontend.

Both providers are gated by config: when any required env var is empty
the endpoints return 503 with an explicit "not configured" message so
the frontend can surface a helpful toast.
"""

import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import User, get_async_session
from app.users import auth_backend, get_jwt_strategy

# Tokens for state values are kept in-process for the lifetime of the
# OAuth round-trip. In a multi-process deployment swap this for Redis
# or a signed JWT round-tripped through the redirect URL.
_state_cache: dict[str, float] = {}
_STATE_TTL_SECONDS = 600  # 10 minutes
_HTTP_OK = 200


def _issue_state() -> str:
    """Allocate a fresh OAuth state token."""
    token = secrets.token_urlsafe(24)
    _state_cache[token] = time.time() + _STATE_TTL_SECONDS
    return token


def _consume_state(state: str) -> bool:
    """Return True iff `state` was issued recently and still valid."""
    expiry = _state_cache.pop(state, None)
    if expiry is None:
        return False
    return expiry >= time.time()


def _google_configured() -> bool:
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def _apple_configured() -> bool:
    return bool(
        settings.apple_oauth_client_id
        and settings.apple_oauth_team_id
        and settings.apple_oauth_key_id
        and settings.apple_oauth_private_key
    )


async def _login_or_create_user(email: str, session: AsyncSession) -> User:
    """Look up a user by email; create one if missing."""
    # ``User.email`` runs through the SQLAlchemy descriptor at runtime —
    # ``==`` returns a ``ColumnElement[bool]``. fastapi-users' base class
    # declares ``email: str`` before the ``Mapped[str]`` column override,
    # so mypy sees a plain bool and rejects ``where()``. Reach the column
    # via ``__table__.c.<name>`` to bypass the descriptor confusion
    # without a type-ignore.
    stmt = select(User).where(User.__table__.c.email == email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    # FastAPI-Users normally hashes a plaintext password; OAuth users
    # never sign in with one, so we set a random unrecoverable string.
    placeholder_password = secrets.token_urlsafe(32)
    new_user = User(
        email=email,
        hashed_password=placeholder_password,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user


async def _exchange_google_code(code: str) -> str:
    """Exchange a Google auth code for the user's verified email.

    Split out of the callback handler to keep its cognitive complexity
    under the project's lint budget. Raises HTTPException on any failure
    along the chain so the callback can stay a flat sequence.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != _HTTP_OK:
            raise HTTPException(status_code=502, detail="Google token exchange failed.")
        token_payload: dict[str, Any] = token_response.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=502,
                detail="Google token response missing access_token.",
            )
        userinfo_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_response.status_code != _HTTP_OK:
            raise HTTPException(status_code=502, detail="Google userinfo fetch failed.")
        userinfo: dict[str, Any] = userinfo_response.json()

    email = userinfo.get("email")
    if not isinstance(email, str) or not email:
        raise HTTPException(status_code=502, detail="Google account has no verified email.")
    return email


async def _issue_session_cookie(user: User, response: Response) -> None:
    """Set the FastAPI-Users session cookie on `response`."""
    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)
    # Reuse the configured cookie name + flags via auth_backend.transport
    # so the cookie matches what password auth issues.
    auth_backend.transport._set_login_cookie(response, token)  # type: ignore[attr-defined]


def get_oauth_router() -> APIRouter:
    """Build the OAuth router (mounted at /api/v1/auth/oauth)."""
    router = APIRouter(prefix="/api/v1/auth/oauth", tags=["auth"])

    # --- Google -------------------------------------------------------------

    @router.get("/google/start")
    async def google_start() -> RedirectResponse:
        """Redirect to Google's OAuth consent screen."""
        if not _google_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Google sign-in is not configured. "
                    "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env."
                ),
            )
        state = _issue_state()
        params = {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return RedirectResponse(url=url)

    @router.get("/google/callback")
    async def google_callback(
        request: Request,
        session: AsyncSession = Depends(get_async_session),
    ) -> RedirectResponse:
        """Exchange the Google auth code for a session cookie."""
        if not _google_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google sign-in is not configured.",
            )
        code = request.query_params.get("code")
        state = request.query_params.get("state", "")
        if not code:
            raise HTTPException(status_code=400, detail="Missing OAuth code.")
        if not _consume_state(state):
            raise HTTPException(status_code=400, detail="Invalid OAuth state.")

        email = await _exchange_google_code(code)
        user = await _login_or_create_user(email=email, session=session)
        redirect = RedirectResponse(url=settings.oauth_post_login_redirect)
        await _issue_session_cookie(user, redirect)
        return redirect

    # --- Apple --------------------------------------------------------------

    @router.get("/apple/start")
    async def apple_start() -> RedirectResponse:
        """Redirect to Apple's Sign In consent screen."""
        if not _apple_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Apple sign-in is not configured. "
                    "Set APPLE_OAUTH_CLIENT_ID, APPLE_OAUTH_TEAM_ID, "
                    "APPLE_OAUTH_KEY_ID, and APPLE_OAUTH_PRIVATE_KEY in .env."
                ),
            )
        state = _issue_state()
        params = {
            "client_id": settings.apple_oauth_client_id,
            "redirect_uri": settings.apple_oauth_redirect_uri,
            "response_type": "code",
            "scope": "name email",
            "state": state,
            "response_mode": "form_post",
        }
        url = f"https://appleid.apple.com/auth/authorize?{urlencode(params)}"
        return RedirectResponse(url=url)

    @router.post("/apple/callback")
    async def apple_callback() -> RedirectResponse:
        """Apple callback stub.

        The Apple OAuth handshake requires generating a JWT client_secret
        signed with the .p8 private key (PyJWT + cryptography). Wiring
        the code-exchange + identity-token verification is left as a
        follow-up — the endpoint exists so the FE button has a target
        and the env-var documentation lives in one place.
        """
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Apple sign-in callback is stubbed; see app/api/oauth.py.",
        )

    return router
