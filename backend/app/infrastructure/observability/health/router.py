"""Health and readiness endpoints.

Two probes:

- ``GET /api/v1/health`` — liveness.  Returns 200 as long as the process
  is up enough to handle a request.  Used by ``docker compose`` and the
  onboarding server-verify button.
- ``GET /api/v1/health/ready`` — readiness.  Verifies that:

  1. PostgreSQL is reachable with a trivial ``SELECT 1``.
  2. At least one LLM provider has a key configured (so the chat
     endpoint can actually serve a turn).

  Returns 200 with a per-check summary on success, 503 with the same
  shape on failure.  Designed for orchestrators that route traffic only
  when the service is *useful*, not just *alive*.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import settings
from app.infrastructure.database.legacy import get_async_session

log = logging.getLogger(__name__)


def get_health_router() -> APIRouter:
    """Build the health router (mounted at /api/v1/health)."""
    router = APIRouter(prefix="/api/v1/health", tags=["health"])

    @router.get("", include_in_schema=False)
    async def liveness() -> JSONResponse:
        """Liveness probe.  Returns 200 unconditionally."""
        return JSONResponse({"status": "ok"})

    @router.get("/ready", include_in_schema=False)
    async def readiness(
        session: AsyncSession = Depends(get_async_session),
    ) -> JSONResponse:
        """Readiness probe.

        Returns 200 only when:
          - Postgres is reachable.
          - At least one LLM provider is configured.

        On any failure the JSON body still lists every check so an
        operator hitting the URL can see exactly which part is broken
        without grepping the logs.
        """
        checks: dict[str, dict[str, Any]] = {}

        # ── 1. Database ──
        try:
            result = await session.execute(text("SELECT 1"))
            scalar = result.scalar_one_or_none()
            checks["database"] = {
                "ok": scalar == 1,
                "detail": None if scalar == 1 else "select-1 returned unexpected value",
            }
        except Exception as exc:
            log.exception("readiness: database check failed")
            checks["database"] = {"ok": False, "detail": str(exc)}

        # ── 2. Providers ──
        provider_status: dict[str, bool] = {
            "google": bool(settings.google_api_key),
            "claude": bool(settings.claude_code_oauth_token),
        }
        configured = [name for name, ok in provider_status.items() if ok]
        checks["providers"] = {
            "ok": len(configured) > 0,
            "configured": configured,
            "detail": None if configured else "no LLM provider keys set",
        }

        all_ok = all(check["ok"] for check in checks.values())
        return JSONResponse(
            {"status": "ready" if all_ok else "not-ready", "checks": checks},
            status_code=200 if all_ok else 503,
        )

    return router
