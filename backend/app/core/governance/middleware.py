"""Starlette middleware that gates the chat path on the per-user cost cap.

Layered so:

* :class:`RequestLoggingMiddleware` runs first (every request gets a
  request-id stamped log line, including 402s).
* :class:`CostBudgetMiddleware` runs next on the chat path only.  Looks
  up cumulative spend in the rolling window for the authenticated
  user and 402s when adding the per-request reservation would exceed
  ``settings.cost_max_per_user_daily_usd``.
* :class:`ChatRateLimitMiddleware` runs last — request-rate cap.

The middleware is intentionally a *separate* check from the per-request
SDK cap (``ClaudeAgentOptions.max_budget_usd``).  The SDK cap stops one
runaway turn; this middleware stops a runaway *user* from grinding
through the whole organisation's budget across many turns.

Identity comes from the JWT cookie via the same mechanism the rate
limiter uses (UUID5 over the cookie).  We don't decode the JWT here —
the auth dep on the chat route already does that.  This middleware only
needs a stable per-user key for the cumulative-spend lookup.

Configuration (all from :class:`app.core.config.Settings`):

* ``cost_tracker_enabled`` — master switch; ``False`` short-circuits.
* ``cost_max_per_user_daily_usd`` — the cap (USD).  ``0`` disables the
  per-user check while still letting per-request enforcement run.
* ``cost_reset_window_hours`` — the rolling window length.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.governance.cost_tracker import (
    CostBudget,
    PostgresCostLedger,
    per_request_reservation_usd,
)
from app.infrastructure.database.legacy import async_session_maker
from app.infrastructure.middleware.rate_limit import CHAT_PATH_PREFIX

logger = logging.getLogger(__name__)


def _identity_from_request(request: Request) -> str | None:
    """Hash the session cookie into a stable per-user key.

    Mirrors :func:`app.core.rate_limit._identity_from_request` so the
    rate limiter and cost gate share an identity definition.  Returns
    ``None`` when the request isn't authenticated — the chat route's
    auth dep will return 401 in that case, no need to double-gate.
    """
    cookie = request.cookies.get("session_token") or request.headers.get("authorization")
    if not cookie:
        return None
    return str(uuid.uuid5(uuid.NAMESPACE_URL, cookie))


# We resolve the user UUID from the auth backend, but at middleware
# time we only have the cookie hash.  The cumulative-spend SQL needs a
# real ``user.id``; we resolve it lazily via a tiny lookup.  This keeps
# the middleware decoupled from fastapi-users internals while still
# letting it hit ``cost_ledger`` directly.
_UserIdLookup = Callable[[Request], Awaitable[uuid.UUID | None]]


class CostBudgetMiddleware(BaseHTTPMiddleware):
    """Refuse chat requests that would push a user past the rolling cap.

    The hot-path implementation opens a fresh ``async_session_maker``
    session, so the chat route's own session isn't held while we
    compute the aggregate.  Failures (DB unavailable, lookup miss) log
    + fail OPEN — the cap is a soft control, and a hard middleware
    failure here would take chat down for everyone.  The Claude SDK's
    per-request ``max_budget_usd`` is still in force when we fail open,
    so the absolute worst case is one over-budget turn.
    """

    def __init__(
        self,
        app: object,
        *,
        user_id_lookup: _UserIdLookup,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._user_id_lookup = user_id_lookup

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Refuse the chat request when cumulative spend would exceed the cap."""
        denial = await self._evaluate(request)
        if denial is not None:
            return denial
        return await call_next(request)

    async def _evaluate(self, request: Request) -> Response | None:  # noqa: PLR0911 — top-down early-out chain reads more clearly than nested branches
        """Return a 402 denial response, or ``None`` to let the request through."""
        if not self._enabled():
            return None
        if not request.url.path.startswith(CHAT_PATH_PREFIX):
            return None

        user_id = await self._user_id_lookup(request)
        if user_id is None:
            return None

        budget = self._budget()
        if budget.max_per_user_window_usd <= 0:
            return None

        try:
            cumulative = await self._cumulative_for_user(user_id, budget.window_hours)
        except Exception:
            # Fail open — see class docstring.
            logger.exception(
                "COST_BUDGET_LOOKUP_FAILED user_id=%s; failing open",
                user_id,
            )
            return None

        reservation = per_request_reservation_usd(budget)
        if cumulative + reservation <= budget.max_per_user_window_usd:
            return None

        remaining = max(0.0, budget.max_per_user_window_usd - cumulative)
        logger.info(
            "COST_BUDGET_DENIED user_id=%s cumulative=%.4f limit=%.4f window_hours=%d",
            user_id,
            cumulative,
            budget.max_per_user_window_usd,
            budget.window_hours,
        )
        return JSONResponse(
            status_code=402,
            content={
                "detail": (
                    f"Cost budget exhausted: ${cumulative:.4f} of "
                    f"${budget.max_per_user_window_usd:.2f} used in the last "
                    f"{budget.window_hours} hours."
                ),
                "remaining_usd": round(remaining, 4),
                "current_usd": round(cumulative, 4),
                "limit_usd": budget.max_per_user_window_usd,
                "window_hours": budget.window_hours,
            },
        )

    @staticmethod
    def _enabled() -> bool:
        return bool(settings.cost_tracker_enabled)

    @staticmethod
    def _budget() -> CostBudget:
        return CostBudget(
            max_per_request_usd=float(settings.cost_max_per_request_usd),
            max_per_user_window_usd=float(settings.cost_max_per_user_daily_usd),
            window_hours=int(settings.cost_reset_window_hours),
        )

    async def _cumulative_for_user(self, user_id: uuid.UUID, window_hours: int) -> float:
        """Aggregate spend in the rolling window via a fresh session."""
        async with async_session_maker() as session:
            ledger = PostgresCostLedger(session=session)
            return await ledger.cumulative_window_usd(user_id=user_id, window_hours=window_hours)


def install_cost_budget_middleware(
    app: object,
    *,
    user_id_lookup: _UserIdLookup,
) -> None:
    """Register :class:`CostBudgetMiddleware` on a FastAPI app.

    Wrapped in a helper so ``main.py`` can keep its middleware order
    explicit without poking at the middleware constructor signature.
    """
    # ``app.add_middleware`` accepts a class + kwargs and instantiates
    # later — same ordering rules as the rest of main.py.  Using the
    # explicit lookup factory pattern keeps the middleware testable
    # without monkey-patching fastapi-users.
    from fastapi import FastAPI  # noqa: PLC0415 — local import keeps governance import-cycle clean

    if not isinstance(app, FastAPI):
        raise TypeError("install_cost_budget_middleware expects a FastAPI app")
    app.add_middleware(CostBudgetMiddleware, user_id_lookup=user_id_lookup)


# ``async_sessionmaker`` is intentionally not used here — exposing the
# import keeps the module-level deps explicit so future maintainers
# spot the DB dependency immediately.
__all__ = [
    "CostBudgetMiddleware",
    "async_sessionmaker",
    "install_cost_budget_middleware",
]
