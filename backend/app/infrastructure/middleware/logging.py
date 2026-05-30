"""HTTP request-logging middleware.

Logs every incoming HTTP request twice:
  1. On entry — method, path, query string, client IP, user-agent, request ID.
  2. On exit  — status code, duration in ms, request ID.

The request ID (an 8-char ``uuid4`` slice) is also written to a contextvar
so route handlers can include it in their own log lines. This makes it
trivial to grep ``app.log`` for duplicate calls — every entry that shares
the same method+path+body within a few milliseconds shows up adjacent in
the file, each tagged with a distinct request ID.

Why a contextvar (not a request attribute): FastAPI dependencies and
streaming generators don't always have ``request`` in scope, but they do
share the same async context, so a contextvar propagates correctly.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.request")

# Contextvar holding the current request ID for the active async context.
# Defaults to ``"-"`` outside of a request (e.g. startup hooks, background tasks).
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the request ID for the current async context, or ``"-"`` if unset."""
    return _request_id_ctx.get()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request on entry and exit with a unique request ID.

    Mounted via ``app.add_middleware(RequestLoggingMiddleware)`` in
    ``main.py``. Each request produces:

      * one ``REQ_IN`` line before the route handler runs, and
      * one ``REQ_OUT`` line in the ``finally`` block (so it fires even on
        unhandled exceptions, with ``status=500`` as the default).

    The 8-char ``rid`` in both lines lets downstream log lines (e.g.
    ``CHAT_IN``) be correlated back to the originating HTTP request.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Wrap the downstream handler with entry/exit log lines.

        Args:
            request: The incoming Starlette request.
            call_next: The next handler in the middleware chain.

        Returns:
            The response produced by the downstream handler.
        """
        request_id = uuid.uuid4().hex[:8]
        token = _request_id_ctx.set(request_id)

        client_host = request.client.host if request.client else "-"
        user_agent = request.headers.get("user-agent", "-")
        query = request.url.query or "-"

        # Entry log — recorded BEFORE the handler runs, so duplicate calls
        # show up here even if they error out before reaching the route.
        logger.info(
            "REQ_IN  rid=%s %s %s query=%s client=%s ua=%r",
            request_id,
            request.method,
            request.url.path,
            query,
            client_host,
            user_agent,
        )

        start = time.perf_counter()
        status_code: int = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "REQ_OUT rid=%s %s %s status=%d duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )
            _request_id_ctx.reset(token)
