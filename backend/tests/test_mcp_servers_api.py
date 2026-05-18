"""HTTP-level tests for the /api/v1/mcp/servers router (#317)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_list_returns_empty_for_user_with_no_servers(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/mcp/servers")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_create_then_list_round_trip(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/mcp/servers",
        json={
            "name": "notion",
            "config": {"transport": "http", "url": "https://mcp.example.com"},
            "status": "enabled",
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "notion"
    assert created["status"] == "enabled"
    assert created["config"]["transport"] == "http"

    listed = await client.get("/api/v1/mcp/servers")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "notion"


@pytest.mark.anyio
async def test_patch_updates_status(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/mcp/servers",
        json={"name": "github", "config": {}, "status": "enabled"},
    )
    server_id = create.json()["id"]

    patch = await client.patch(
        f"/api/v1/mcp/servers/{server_id}",
        json={"name": "github", "config": {}, "status": "disabled"},
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "disabled"


@pytest.mark.anyio
async def test_patch_missing_returns_404(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/v1/mcp/servers/00000000-0000-0000-0000-000000000000",
        json={"name": "x", "config": {}, "status": "enabled"},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_delete_removes_server(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/mcp/servers",
        json={"name": "temp", "config": {}, "status": "enabled"},
    )
    server_id = create.json()["id"]

    delete = await client.delete(f"/api/v1/mcp/servers/{server_id}")
    assert delete.status_code == 204

    listed = await client.get("/api/v1/mcp/servers")
    assert listed.json() == []


@pytest.mark.anyio
async def test_delete_missing_returns_404(client: AsyncClient) -> None:
    response = await client.delete("/api/v1/mcp/servers/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_create_rejects_invalid_status(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/mcp/servers",
        json={"name": "x", "config": {}, "status": "weird"},
    )
    assert response.status_code == 422
