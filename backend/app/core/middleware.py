"""Custom ASGI / Starlette middleware for Pawrrtal.

Currently provides:
  BackendApiKeyMiddleware — reject requests that don't carry the correct
    ``X-Pawrrtal-Key`` header when ``BACKEND_API_KEY`` is configured.
"""

import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

# Paths that bypass the API-key check so health probes and the OpenAPI
# docs remain reachable without a key even in locked-down deployments.
_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    # OAuth start redirects initiate from the browser; no key there.
    "/api/v1/auth/oauth/",
)


class BackendApiKeyMiddleware(BaseHTTPMiddleware):
    """Require the ``X-Pawrrtal-Key`` header on every non-exempt request.

    Only active when ``BACKEND_API_KEY`` is configured. Returning a 401
    at the transport layer prevents unauthenticated parties from even
    reaching the FastAPI router, so the email allowlist (``ALLOWED_EMAILS``)
    is the second, identity-level gate that runs after a user is logged in.

    Uses ``secrets.compare_digest`` to avoid timing side-channels when
    comparing the supplied key against the configured value.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Validate the configured backend API key before routing the request."""
        # If no key is configured, the middleware is effectively disabled.
        if not settings.backend_api_key:
            return await call_next(request)

        # Exempt paths bypass the key check.
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        provided = request.headers.get("X-Pawrrtal-Key", "")
        # compare_digest requires both operands to be the same type and
        # non-empty; fall back to a dummy comparison to keep constant time.
        expected = settings.backend_api_key
        if not secrets.compare_digest(
            provided.encode() if provided else b"",
            expected.encode(),
        ):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Missing or invalid X-Pawrrtal-Key header. "
                        "This backend requires an API key to connect."
                    )
                },
            )

        return await call_next(request)
