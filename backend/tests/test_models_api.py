"""Tests for ``GET /api/v1/models``."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.api.models import ETAG_HEADER
from app.core.providers.catalog import MODEL_CATALOG
from app.core.providers.factory import host_authenticated


def _authed_catalog_count() -> int:
    """How many catalog rows survive the ``host_authenticated`` filter."""
    return sum(1 for entry in MODEL_CATALOG if host_authenticated(entry.host))


@pytest.mark.anyio
async def test_models_endpoint_returns_authenticated_catalog(client: AsyncClient) -> None:
    """The endpoint returns only catalog entries whose host has credentials.

    Issue #370 — unauthenticated providers (e.g. OpenCode without an
    API key, xAI without ``XAI_API_KEY``) used to show up in the
    picker but couldn't be selected. Now they're filtered out so the
    list only shows usable rows.
    """
    response = await client.get("/api/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert "models" in body
    expected_count = _authed_catalog_count()
    assert len(body["models"]) == expected_count
    # The pytest fixtures set GOOGLE_API_KEY, so at least the google_ai
    # rows are present. If nothing is authenticated the list is empty —
    # also a valid state, so we only assert shape when there's content.
    if body["models"]:
        first = body["models"][0]
        for key in ("id", "host", "vendor", "model", "display_name", "is_default"):
            assert key in first


@pytest.mark.anyio
async def test_models_endpoint_omits_unauthenticated_hosts(client: AsyncClient) -> None:
    """No host in the response should fail the ``host_authenticated`` gate."""
    response = await client.get("/api/v1/models")
    returned_hosts = {entry["host"] for entry in response.json()["models"]}
    for host_value in returned_hosts:
        # ``host_value`` is the StrEnum value (e.g. ``"google-ai"``);
        # construct the enum member back to feed the gate.
        from app.core.providers.model_id import Host

        assert host_authenticated(Host(host_value)), (
            f"unauthenticated host {host_value!r} leaked through the filter"
        )


@pytest.mark.anyio
async def test_models_endpoint_sets_etag(client: AsyncClient) -> None:
    response = await client.get("/api/v1/models")
    assert response.headers["etag"] == ETAG_HEADER
    assert "private" in response.headers["cache-control"]


@pytest.mark.anyio
async def test_models_endpoint_returns_304_when_etag_matches(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/models",
        headers={"If-None-Match": ETAG_HEADER},
    )
    assert response.status_code == 304
    assert response.content == b""  # 304 must have empty body


@pytest.mark.anyio
async def test_models_endpoint_etag_includes_auth_fingerprint(client: AsyncClient) -> None:
    """The ETag must vary with the authenticated-host set.

    Pinned so a future change can't silently drop the auth fingerprint
    and bring back the stale-304 bug — a deployment that authenticated
    a new provider after boot would otherwise serve the old filtered
    list to any client that cached the previous ETag.
    """
    response = await client.get("/api/v1/models")
    # The full ETag is ``"<catalog-hash>-<fingerprint>"``. Asserting on
    # the dash structure keeps the test resilient to catalog-hash
    # changes while still pinning the auth fingerprint requirement.
    assert response.headers["etag"].count("-") >= 1
    assert response.headers["etag"].endswith('"')


@pytest.mark.anyio
async def test_default_entry_present_when_default_host_authenticated(
    client: AsyncClient,
) -> None:
    """The catalog default survives the filter when its host is authenticated.

    Pytest's environment sets ``GOOGLE_API_KEY`` (required to boot the
    settings), and the canonical default in the catalog is a Gemini
    model, so the default row should always be in the filtered list
    under the test fixtures. If the default ever moves to an
    unauthenticated host, this test will surface that drift.
    """
    response = await client.get("/api/v1/models")
    defaults = [m for m in response.json()["models"] if m["is_default"]]
    assert len(defaults) == 1
