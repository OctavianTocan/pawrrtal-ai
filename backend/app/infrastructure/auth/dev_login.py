from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.infrastructure.auth.users import (
    UserManager,
    auth_backend,
    get_jwt_strategy,
    get_user_manager,
)
from app.infrastructure.config import settings


def _safe_redirect_path(value: object) -> str:
    if not isinstance(value, str):
        return "/"
    stripped = value.strip()
    if not stripped.startswith("/") or stripped.startswith("//") or "\\" in stripped:
        return "/"
    return stripped


async def _form_redirect_target(request: Request) -> str | None:
    redirect_query = request.query_params.get("redirect_to")
    if redirect_query is not None:
        return _safe_redirect_path(redirect_query)

    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in content_type:
        return None

    form = await request.form()
    if "redirect_to" not in form:
        return None
    return _safe_redirect_path(form.get("redirect_to"))


def _redirect_with_login_cookie(login_response: Response, redirect_to: str) -> RedirectResponse:
    redirect = RedirectResponse(url=redirect_to, status_code=status.HTTP_303_SEE_OTHER)
    for header_name, header_value in login_response.raw_headers:
        if header_name.lower() == b"set-cookie":
            redirect.raw_headers.append((header_name, header_value))
    return redirect


async def _dev_login_response(
    request: Request,
    user_manager: UserManager,
    fallback_redirect: str | None,
) -> Response:
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

    login_response = await auth_backend.login(get_jwt_strategy(), user)
    redirect_to = await _form_redirect_target(request)
    if redirect_to is None:
        if fallback_redirect is None:
            return login_response
        redirect_to = fallback_redirect
    return _redirect_with_login_cookie(login_response, redirect_to)


def get_auth_router() -> APIRouter:
    """Build the auth ``APIRouter`` exposing the dev-login helper endpoint."""
    router = APIRouter(tags=["auth"])

    @router.post("/auth/dev-login")
    async def dev_login(
        request: Request,
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
        return await _dev_login_response(request, user_manager, fallback_redirect=None)

    @router.post("/auth/dev-login/browser")
    async def dev_login_browser(
        request: Request,
        user_manager: UserManager = Depends(get_user_manager),
    ) -> Response:
        """Log in from server-rendered browser forms before React hydrates."""
        return await _dev_login_response(request, user_manager, fallback_redirect="/")

    return router
