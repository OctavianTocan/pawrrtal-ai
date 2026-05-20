"""Tests for the /api/v1/health liveness-probe endpoint.

The health endpoint is added in feat/onboarding-revamp to support the
onboarding step-server "Verify" button.  It must be:

1. Publicly accessible — no authentication required.  The verify button
   is clicked *before* the user has a session (they're checking that the
   remote URL resolves to a real Pawrrtal server).
2. Always fast — no database round-trips, no network calls.
3. Structurally stable — the exact JSON shape ``{"status": "ok"}`` is
   what the frontend pings; changing it is a breaking wire change.

These tests prove all three properties hold and will catch regressions
if the endpoint is accidentally gated, moved, or its response changed.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import create_app  # noqa: E402 — sys.path tweak above must precede

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def unauthenticated_app():
    """A bare FastAPI app with NO dependency overrides.

    Uses the real ``create_app()`` factory but with an in-memory DB so it
    can boot without a running Postgres.  Crucially, no
    ``current_active_user`` override is applied — this proves the health
    endpoint is truly public.
    """
    import os

    # Point the app at an in-memory SQLite so the lifespan startup doesn't
    # fail on a missing Postgres DSN.
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-not-real")
    os.environ.setdefault("WORKSPACE_ENCRYPTION_KEY", "A" * 44)

    return create_app()


@pytest.fixture
async def raw_client(unauthenticated_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Async HTTP client talking to an unauthenticated app instance."""
    transport = ASGITransport(app=unauthenticated_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests using the standard auth-overridden client (from conftest)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health_returns_200(client: AsyncClient) -> None:
    """Health endpoint responds with HTTP 200 OK."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_health_response_body_is_status_ok(client: AsyncClient) -> None:
    """Health endpoint returns exactly ``{"status": "ok"}``.

    The frontend pings this exact shape — it is a wire contract.
    """
    response = await client.get("/api/v1/health")
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_health_content_type_is_json(client: AsyncClient) -> None:
    """Health response Content-Type must be application/json.

    The onboarding verify button inspects the JSON body; non-JSON
    responses would fail silently on the client side.
    """
    response = await client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]


@pytest.mark.anyio
async def test_health_is_idempotent_across_multiple_calls(
    client: AsyncClient,
) -> None:
    """Health endpoint returns the same result every time it is called.

    Simulates the verify button being clicked repeatedly without a page
    reload — all calls must succeed with the same body.
    """
    results = []
    for _ in range(5):
        r = await client.get("/api/v1/health")
        results.append((r.status_code, r.json()))

    assert all(status == 200 for status, _ in results)
    assert all(body == {"status": "ok"} for _, body in results)


# ---------------------------------------------------------------------------
# Tests using the raw unauthenticated client
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health_is_accessible_without_authentication(
    raw_client: AsyncClient,
) -> None:
    """Health endpoint must NOT require a logged-in session.

    The whole point of this endpoint is to be called before the user has
    authenticated (during the onboarding server-configuration step).  If
    it were gated by ``current_active_user`` it would always return 401
    for new users, making the verify button useless.
    """
    response = await raw_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_health_not_401_for_anonymous_client(raw_client: AsyncClient) -> None:
    """Health endpoint must not redirect to login or return 401/403.

    Belt-and-suspenders assertion: explicitly confirm that unauthenticated
    callers are not denied access.
    """
    response = await raw_client.get("/api/v1/health")
    assert response.status_code not in (401, 403), (
        f"Health endpoint rejected unauthenticated request with "
        f"{response.status_code}: {response.text}"
    )


@pytest.mark.anyio
async def test_health_endpoint_at_canonical_path(raw_client: AsyncClient) -> None:
    """The endpoint is at exactly /api/v1/health — canonical path must not drift.

    If the router prefix changes (e.g. /api/v2/health) the onboarding
    frontend would silently break.  Locking this path in a test makes the
    drift visible immediately.
    """
    # Correct path.
    good = await raw_client.get("/api/v1/health")
    assert good.status_code == 200

    # Wrong paths must NOT return 200.
    wrong_paths = ["/health", "/api/health", "/api/v2/health"]
    for path in wrong_paths:
        r = await raw_client.get(path)
        assert r.status_code != 200, f"Unexpected 200 at {path!r} — path drift may have occurred"
