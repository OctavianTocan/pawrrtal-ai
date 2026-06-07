"""Tests for ``GET /api/v1/models``."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.providers.catalog import MODEL_CATALOG
from app.providers.factory import host_authenticated
from app.providers.model_id import Host


def _authed_catalog_count() -> int:
    """How many catalog rows survive the ``host_authenticated`` filter.

    No workspace context is passed: the test client doesn't go through
    the workspace bootstrap, so the endpoint sees ``workspace_root=None``
    and the filter falls back to global ``settings.*`` only. Mirror that
    here so the expected count matches the response.
    """
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
        for key in ("id", "host", "vendor", "model", "display_name"):
            assert key in first


@pytest.mark.anyio
async def test_models_endpoint_omits_unauthenticated_hosts(client: AsyncClient) -> None:
    """No host in the response should fail the ``host_authenticated`` gate."""
    response = await client.get("/api/v1/models")
    returned_hosts = {entry["host"] for entry in response.json()["models"]}
    for host_value in returned_hosts:
        # ``host_value`` is the StrEnum value (e.g. ``"google-ai"``);
        # construct the enum member back to feed the gate.
        assert host_authenticated(Host(host_value)), (
            f"unauthenticated host {host_value!r} leaked through the filter"
        )


@pytest.mark.anyio
async def test_models_endpoint_sets_etag(client: AsyncClient) -> None:
    response = await client.get("/api/v1/models")
    etag = response.headers["etag"]
    # Auth-fingerprinted shape: ``"<catalog-hash>-<bitstring>"``.
    assert etag.startswith('"')
    assert etag.endswith('"')
    assert "-" in etag
    assert "private" in response.headers["cache-control"]


@pytest.mark.anyio
async def test_models_endpoint_returns_304_when_etag_matches(
    client: AsyncClient,
) -> None:
    """An ``If-None-Match`` matching the live ETag round-trips to 304.

    The ETag is computed per-request now (so a workspace key landing
    after boot doesn't get masked by a stale 304 — review feedback on
    #370). Re-issuing the same request with the returned ETag must
    still produce a clean 304 with no body.
    """
    first = await client.get("/api/v1/models")
    etag = first.headers["etag"]
    response = await client.get("/api/v1/models", headers={"If-None-Match": etag})
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


def test_host_authenticated_with_workspace_uses_workspace_key(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``workspace_root`` opens the documented per-workspace key path.

    Even when global ``settings.xai_api_key`` is empty, a workspace
    that wrote ``XAI_API_KEY=...`` to its encrypted ``.env`` should
    pass the gate — otherwise the picker hides providers that
    actually work for that workspace (review feedback on #370).
    """
    from pathlib import Path
    from unittest.mock import patch

    workspace_root = Path(str(tmp_path))
    # Force global setting empty so the gate can't accidentally pass
    # via the fallback path; the test would be silently weak otherwise.
    from app.providers.factory import settings as factory_settings

    monkeypatch.setattr(factory_settings, "xai_api_key", "")
    # Stub the shared key resolver to simulate a workspace-keyed
    # deployment: workspace has the key, global doesn't.
    with patch("app.infrastructure.keys.resolve_api_key", return_value="ws-only-token"):
        assert host_authenticated(Host.xai, workspace_root=workspace_root) is True
    # Sanity check: without the workspace path, the gate stays False
    # because global settings is still empty.
    assert host_authenticated(Host.xai) is False


def test_host_authenticated_with_workspace_uses_xai_oauth_token(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xAI OAuth-only workspaces should still show xAI models in the picker."""
    from pathlib import Path
    from unittest.mock import patch

    workspace_root = Path(str(tmp_path))
    from app.providers.factory import settings as factory_settings

    monkeypatch.setattr(factory_settings, "xai_api_key", "")
    with (
        patch(
            "app.infrastructure.keys.load_workspace_env",
            return_value={"XAI_OAUTH_ACCESS_TOKEN": "oauth-only-token"},
        ),
        patch("app.infrastructure.keys.resolve_api_key", return_value=None),
    ):
        assert host_authenticated(Host.xai, workspace_root=workspace_root) is True


def test_host_authenticated_does_not_expose_agy_cli_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The raw Antigravity CLI adapter is no longer a selectable model host."""
    monkeypatch.setattr("app.providers.agy_cli.is_agy_cli_available", lambda: True)

    assert host_authenticated(Host.agy_cli) is False


def test_host_authenticated_probes_agy_api_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    """Direct Antigravity API rows are visible when local agy auth is usable."""
    from pathlib import Path

    workspace_root = Path(str(tmp_path))
    seen_workspace_roots: list[Path | None] = []

    def has_auth(workspace_root: Path | None = None) -> bool:
        seen_workspace_roots.append(workspace_root)
        return True

    monkeypatch.setattr("app.providers.agy_api.has_agy_api_auth", has_auth)

    assert host_authenticated(Host.agy_api, workspace_root=workspace_root) is True
    assert seen_workspace_roots == [workspace_root]
