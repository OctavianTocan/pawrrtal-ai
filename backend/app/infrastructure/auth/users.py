"""User management and authentication using FastAPI-Users. This module defines the UserManager class that handles user lifecycle events (registration, login, etc.) and sets up the authentication backend using JWTs stored in secure cookies. It also provides FastAPI dependencies for accessing the user manager and the current active user."""

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, Response
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    UUIDIDMixin,
)
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from app.core.config import settings
from app.infrastructure.database.legacy import User, get_user_db

MIN_PASSWORD_LENGTH = 8


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Handles user lifecycle events (registration, login, password reset)."""

    reset_password_token_secret = settings.auth_secret
    verification_token_secret = settings.auth_secret

    async def validate_password(self, password: str, user: object) -> None:
        """Enforce minimum password length."""
        if len(password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            )

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        """Hook called after a new user registers."""

    async def on_after_login(
        self,
        user: User,
        request: Request | None = None,
        response: Response | None = None,
    ) -> None:
        """Hook called after a user logs in."""


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db),
) -> AsyncGenerator[UserManager]:
    """FastAPI dependency that yields a ``UserManager`` instance."""
    yield UserManager(user_db)


# --- Transport & Strategy ---------------------------------------------------

should_secure_cookie = (
    settings.cookie_secure if settings.cookie_secure is not None else settings.is_production
)  # Use secure cookies if requested, otherwise fallback to is_production

cookie_transport = CookieTransport(
    cookie_name="session_token",
    cookie_httponly=True,
    cookie_secure=should_secure_cookie,
    cookie_samesite=settings.cookie_samesite,
    cookie_max_age=3600,
    cookie_domain=settings.cookie_domain,
)


def get_jwt_strategy() -> JWTStrategy[User, uuid.UUID]:
    """Create a JWT strategy with a 1-hour lifetime."""
    return JWTStrategy(secret=settings.auth_secret, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

# --- FastAPI-Users instance --------------------------------------------------

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)


async def get_allowed_user(user: User = Depends(current_active_user)) -> User:
    """Email-allowlist identity gate layered on top of ``current_active_user``.

    When ``settings.allowed_emails`` is empty the deployment is open to any
    authenticated user (useful for local dev).  When set, only users whose
    lowercased email appears in the comma-separated list may access the
    protected route.  Apply this dependency to every route that should be
    private to the deployment's permitted users.

    Raises ``403 This Pawrrtal deployment is private.`` for unauthorized
    callers — a deliberately generic message so a stranger probing the
    endpoint can't enumerate which emails are allowed.
    """
    allowed = settings.allowed_emails_set
    if allowed and user.email.lower() not in allowed:
        raise HTTPException(
            status_code=403,
            detail="This Pawrrtal deployment is private.",
        )
    return user
