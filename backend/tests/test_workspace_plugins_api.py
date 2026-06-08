"""HTTP-level tests for workspace plugin management."""

from __future__ import annotations

import uuid
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Workspace
from app.plugins.state import PluginState, load_plugin_state, plugin_state_path, save_plugin_state


def _plugin_by_id(body: dict[str, object], plugin_id: str) -> dict[str, object]:
    """Return a plugin row from a response body."""
    plugins = body["plugins"]
    assert isinstance(plugins, list)
    for plugin in plugins:
        assert isinstance(plugin, dict)
        if plugin["plugin_id"] == plugin_id:
            return plugin
    raise AssertionError(f"plugin {plugin_id!r} not found")


def _capability_by_key(plugin: dict[str, object], key: str) -> dict[str, object]:
    """Return a capability row from a plugin row."""
    capabilities = plugin["capabilities"]
    assert isinstance(capabilities, list)
    for capability in capabilities:
        assert isinstance(capability, dict)
        if capability["key"] == key:
            return capability
    raise AssertionError(f"capability {key!r} not found")


@pytest.mark.anyio
async def test_plugins_list_includes_bundled_enabled_and_disabled_plugins(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.get(f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins")

    assert response.status_code == 200
    body = response.json()
    tasks = _plugin_by_id(body, "tasks")
    python_shell = _plugin_by_id(body, "python_shell")
    assert tasks["status"] == "active"
    assert tasks["enabled"] is True
    assert tasks["manageable"] is True
    assert tasks["manage_reason"] is None
    assert python_shell["status"] == "disabled"
    assert python_shell["enabled"] is False
    assert _capability_by_key(tasks, "tasks/add_task")["state"] == "enabled"


@pytest.mark.anyio
async def test_plugins_patch_enables_disabled_plugin(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.patch(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins/python_shell",
        json={"enabled": True},
    )

    assert response.status_code == 200
    python_shell = _plugin_by_id(response.json(), "python_shell")
    assert python_shell["status"] == "active"
    assert python_shell["enabled"] is True
    capability = _capability_by_key(python_shell, "python_shell/python")
    assert capability["state"] == "enabled"
    assert capability["requires_confirmation"] is True

    state = load_plugin_state(
        plugin_state_path(
            plugin_id="python_shell",
            scope="workspace",
            workspace_root=Path(seeded_default_workspace.path),
        ),
        enabled_by_default=False,
        source_type="workspace",
    )
    assert state.enabled is True


@pytest.mark.anyio
async def test_channel_plugins_are_runtime_global_not_workspace_manageable(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.get(f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins")

    assert response.status_code == 200
    core_channels = _plugin_by_id(response.json(), "core_channels")
    assert core_channels["status"] == "active"
    assert core_channels["enabled"] is True
    assert core_channels["manageable"] is False
    assert "runtime-global channel adapters" in str(core_channels["manage_reason"])


@pytest.mark.anyio
async def test_plugins_patch_rejects_runtime_global_channel_plugin(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.patch(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins/core_channels",
        json={"enabled": False},
    )

    assert response.status_code == 400
    assert "runtime-global channel adapters" in response.text


@pytest.mark.anyio
async def test_channel_plugin_list_ignores_stale_workspace_state(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    workspace_root = Path(seeded_default_workspace.path)
    save_plugin_state(
        plugin_state_path(
            plugin_id="core_channels",
            scope="workspace",
            workspace_root=workspace_root,
        ),
        PluginState(enabled=False),
    )

    response = await client.get(f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins")

    assert response.status_code == 200
    core_channels = _plugin_by_id(response.json(), "core_channels")
    assert core_channels["status"] == "active"
    assert core_channels["enabled"] is True
    assert core_channels["manageable"] is False


@pytest.mark.anyio
async def test_plugins_patch_rejects_unknown_plugin(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.patch(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins/nope",
        json={"enabled": True},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_plugins_slot_preference_marks_capability_preferred(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins/slots/tasks",
        json={"capability_key": "tasks/list_tasks"},
    )

    assert response.status_code == 200
    tasks = _plugin_by_id(response.json(), "tasks")
    list_tasks = _capability_by_key(tasks, "tasks/list_tasks")
    add_task = _capability_by_key(tasks, "tasks/add_task")
    assert list_tasks["preferred"] is True
    assert add_task["preferred"] is False


@pytest.mark.anyio
async def test_plugins_slot_preference_rejects_channel_capability(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins/slots/channel:telegram",
        json={"capability_key": "telegram_channel/telegram"},
    )

    assert response.status_code == 400
    assert "runtime-global channel adapters" in response.text


@pytest.mark.anyio
async def test_plugins_slot_preference_rejects_wrong_slot(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    response = await client.put(
        f"/api/v1/workspaces/{seeded_default_workspace.id}/plugins/slots/web_search",
        json={"capability_key": "tasks/list_tasks"},
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_plugins_do_not_leak_between_users(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    other_root = tmp_path / "other-workspace"
    other_root.mkdir()
    other = Workspace(
        id=uuid4(),
        user_id=uuid.uuid4(),
        name="Other",
        slug="other",
        path=str(other_root),
        is_default=False,
    )
    db_session.add(other)
    await db_session.commit()

    response = await client.get(f"/api/v1/workspaces/{other.id}/plugins")

    assert response.status_code == 404
