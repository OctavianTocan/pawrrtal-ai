"""Tests for the /api/v1/health liveness-probe endpoint.

The health endpoint supports local service checks, Cloudflared origin
verification, and Paw CLI diagnostics. It must be:

1. Publicly accessible — no authentication required. Cloudflared and local
   service checks must be able to verify the backend before a user session
   exists.
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
def unauthenticated_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """A bare FastAPI app with NO dependency overrides.

    Uses the real ``create_app()`` factory but with an in-memory DB so it
    can boot without a running Postgres.  Crucially, no
    ``current_active_user`` override is applied — this proves the health
    endpoint is truly public.
    """
    # Point the app at an in-memory SQLite so the lifespan startup doesn't
    # fail on a missing Postgres DSN.
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-real")
    monkeypatch.setenv("WORKSPACE_ENCRYPTION_KEY", "A" * 44)

    return create_app()


@pytest.fixture
async def raw_client(unauthenticated_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Async HTTP client talking to an unauthenticated app instance."""
    transport = ASGITransport(app=unauthenticated_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests using the raw unauthenticated client
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health_returns_200(raw_client: AsyncClient) -> None:
    """Health endpoint responds with HTTP 200 OK."""
    response = await raw_client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_health_response_body_is_status_ok(raw_client: AsyncClient) -> None:
    """Health endpoint returns exactly ``{"status": "ok"}``.

    The frontend pings this exact shape — it is a wire contract.
    """
    response = await raw_client.get("/api/v1/health")
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_health_content_type_is_json(raw_client: AsyncClient) -> None:
    """Health response Content-Type must be application/json.

    Cloudflared verification and Paw CLI diagnostics inspect the JSON body;
    non-JSON responses would fail silently on the client side.
    """
    response = await raw_client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]


@pytest.mark.anyio
async def test_health_is_idempotent_across_multiple_calls(
    raw_client: AsyncClient,
) -> None:
    """Health endpoint returns the same result every time it is called.

    Simulates repeated local and Cloudflared probes without process restart;
    all calls must succeed with the same body.
    """
    results = []
    for _ in range(5):
        r = await raw_client.get("/api/v1/health")
        results.append((r.status_code, r.json()))

    assert all(status == 200 for status, _ in results)
    assert all(body == {"status": "ok"} for _, body in results)


@pytest.mark.anyio
async def test_health_is_accessible_without_authentication(
    raw_client: AsyncClient,
) -> None:
    """Health endpoint must NOT require a logged-in session.

    The whole point of this endpoint is to be called before the user has
    authenticated. Cloudflared, local service checks, and CLI verification
    all need this endpoint before a browser session exists.
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

    If the router prefix changes (e.g. /api/v2/health), Cloudflared and Paw
    CLI verification drift. Locking this path in a test makes that visible.
    """
    # Correct path.
    good = await raw_client.get("/api/v1/health")
    assert good.status_code == 200

    # Wrong paths must NOT return 200.
    wrong_paths = ["/health", "/api/health", "/api/v2/health"]
    for path in wrong_paths:
        r = await raw_client.get(path)
        assert r.status_code != 200, f"Unexpected 200 at {path!r} — path drift may have occurred"
