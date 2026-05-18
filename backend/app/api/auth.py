import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.workspace import ensure_default_workspace
from app.db import get_async_session
from app.users import UserManager, auth_backend, get_jwt_strategy, get_user_manager

logger = logging.getLogger(__name__)


def get_auth_router() -> APIRouter:
    """Build the auth ``APIRouter`` exposing the dev-login helper endpoint."""
    router = APIRouter(tags=["auth"])

    @router.post("/auth/dev-login")
    async def dev_login(
        user_manager: UserManager = Depends(get_user_manager),
        session: AsyncSession = Depends(get_async_session),
    ) -> Response:
        """Log in with the seeded admin account without exposing its password to the client.

        Auto-provisions a default workspace for the admin user when none
        exists yet. The web app refuses to render the sidebar until the
        active user has a default workspace (`onboarding-status`); without
        this step, Playwright suites that drive the seeded admin land on
        the onboarding wizard instead of the home shell. Personalization
        upsert still creates one for real users via
        :func:`app.crud.workspace.ensure_default_workspace` — this call
        just hits the same idempotent path earlier so dev-login is enough
        to land on a fully rendered app.
        """
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dev login is not available in production.",
            )

        if (not settings.admin_email) or (not settings.admin_password):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dev login is not configured on this deployment.",
            )

        credentials = OAuth2PasswordRequestForm(
            grant_type="password",
            username=settings.admin_email,
            password=settings.admin_password,
            scope="",
        )
        user = await user_manager.authenticate(credentials)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dev login credentials are misconfigured on this deployment.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The dev admin account is inactive.",
            )

        # Idempotent — returns the existing workspace if one is already
        # present. Errors here are logged + swallowed: a failed seed
        # must never block dev-login (the user can still personalise
        # via the UI to get a workspace).
        try:
            await ensure_default_workspace(user.id, session)
        except Exception:
            logger.exception("DEV_LOGIN_WORKSPACE_SEED_FAILED user_id=%s", user.id)

        return await auth_backend.login(get_jwt_strategy(), user)

    return router
