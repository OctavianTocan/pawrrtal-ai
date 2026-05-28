"""In-memory per-user rate limiter for the chat endpoint.

A runaway client (bug, hostile user, infinite loop) can otherwise burn
the entire token budget for the deployment in minutes.  This module
caps each user to a configurable number of chat requests per minute.

Design notes
------------
- **Per-user, not per-IP.**  The chat endpoint requires an authenticated
  user so we already have a stable identity key.  IP-based limits would
  punish users on the same NAT (offices, mobile carriers) and not stop
  a logged-in attacker.
- **In-memory.**  Pawrrtal runs single-worker today.  When we scale to
  multi-worker uvicorn or multi-host, swap the storage for Redis
  without changing the Starlette middleware interface.  The pluggable
  ``RateLimitStorage`` protocol below makes that swap localised.
- **Sliding window, not fixed window.**  Fixed windows let a user burst
  ``2 * limit`` requests across a window boundary.  We use a simple
  per-user deque of request timestamps trimmed to the last 60 s.
- **Only enforces on chat.**  This is the only endpoint that makes a
  paid upstream call per request.  The middleware short-circuits any
  other path immediately.

Configuration
-------------
``settings.chat_rate_limit_per_minute`` (int, default 30).  Zero
disables the limit entirely — useful for local development.

Response on limit
-----------------
``429 Too Many Requests`` with ``Retry-After`` set to the seconds until
the oldest in-window request ages out, plus a JSON body explaining the
limit so the frontend can render a clean message instead of a generic
error toast.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

log = logging.getLogger(__name__)

CHAT_PATH_PREFIX = "/api/v1/chat"
WINDOW_SECONDS = 60.0


class RateLimitStorage(Protocol):
    """Pluggable storage so the in-memory backend can be swapped for Redis."""

    def record_and_count(self, key: str, now: float, window: float) -> tuple[int, float]:
        """Append *now* and return ``(count_in_window, oldest_timestamp_in_window)``."""
        ...


class InMemoryWindow(RateLimitStorage):
    """Per-key deque trimmed to a rolling time window.

    Not thread-safe — uvicorn workers are single-threaded per request
    loop so this is fine.  Promote to ``asyncio.Lock`` per key if that
    assumption ever breaks.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}

    def record_and_count(self, key: str, now: float, window: float) -> tuple[int, float]:
        """Append *now* to *key*'s rolling window and return its current size."""
        bucket = self._windows.setdefault(key, deque())
        cutoff = now - window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        bucket.append(now)
        return (len(bucket), bucket[0] if bucket else now)


_storage = InMemoryWindow()


def _identity_from_request(request: Request) -> str | None:
    """Extract a stable per-user key from the JWT cookie.

    Returns ``None`` for anonymous requests — those should already be
    rejected by the auth dep on the route itself; we don't double-limit
    them here.
    """
    # fastapi-users sets ``session_token`` as a JWT in the cookie.  We
    # don't want to parse it here (that's the auth backend's job) so we
    # just hash the raw cookie value, which is stable per session.
    cookie = request.cookies.get("session_token") or request.headers.get("authorization")
    if not cookie:
        return None
    # Use a UUID5 over the cookie so the key has a fixed length and
    # doesn't expose the raw token in logs if we ever surface keys.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, cookie))


class ChatRateLimitMiddleware(BaseHTTPMiddleware):
    """Cap chat requests per user per minute.

    Layered above ``RequestLoggingMiddleware`` so 429s still get a
    request-id stamped log line, and below ``BackendApiKeyMiddleware``
    so a request without the API key never reaches the limiter (and
    thus can't be used to enumerate the limit's existence).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Apply the per-user rate limit, returning 429 when the window is full."""
        limit = settings.chat_rate_limit_per_minute
        if limit <= 0:
            return await call_next(request)
        if not request.url.path.startswith(CHAT_PATH_PREFIX):
            return await call_next(request)

        identity = _identity_from_request(request)
        if identity is None:
            # No session cookie — let the auth dep on the route handler
            # return its 401.  The limit is per-user, not per-anonymous.
            return await call_next(request)

        now = time.monotonic()
        count, oldest = _storage.record_and_count(identity, now, WINDOW_SECONDS)
        if count > limit:
            retry_after = max(1, int(WINDOW_SECONDS - (now - oldest)))
            log.info(
                "RATE_LIMIT path=%s identity=%s count=%d limit=%d retry_after=%ds",
                request.url.path,
                identity[:8],  # truncated — log enough to correlate, not enough to impersonate
                count,
                limit,
                retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limit exceeded: {limit} chat requests per minute. "
                        f"Try again in {retry_after} seconds."
                    ),
                    "retry_after_seconds": retry_after,
                    "limit": limit,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


def reset_rate_limit_storage_for_tests() -> None:
    """Test helper — wipes the in-memory storage between cases.

    Pytest fixtures call this in ``setup`` so per-user windows from one
    test don't bleed into the next.
    """
    _storage._windows.clear()
