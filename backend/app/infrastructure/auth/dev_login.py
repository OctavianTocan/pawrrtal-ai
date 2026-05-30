from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordRequestForm

from app.infrastructure.auth.users import (
    UserManager,
    auth_backend,
    get_jwt_strategy,
    get_user_manager,
)
from app.infrastructure.config import settings


def get_auth_router() -> APIRouter:
    """Build the auth ``APIRouter`` exposing the dev-login helper endpoint."""
    router = APIRouter(tags=["auth"])

    @router.post("/auth/dev-login")
    async def dev_login(
        user_manager: UserManager = Depends(get_user_manager),
    ) -> Response:
        """Log in with the seeded admin account without exposing its password to the client.

        The dev-login endpoint is intentionally minimal: it authenticates
        the seeded admin and returns the session cookie. It does **not**
        seed a workspace — that's left to the personalization flow so
        Playwright suites can drive both pre-onboarding and post-onboarding
        states independently. The workspace seed lives in the
        ``authenticatedPageWithWorkspace`` fixture in
        ``frontend/e2e/fixtures.ts`` for tests that need a fully-rendered
        home shell.
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

        return await auth_backend.login(get_jwt_strategy(), user)

    return router
