"""Tests for manifest-backed turn context providers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from app.plugins.active_recall import recall_agent
from app.plugins.adapters.turn_context import (
    TurnContextProviderContext,
    build_turn_context_providers,
)
from app.plugins.discovery import PluginRoot, discover_plugins
from app.plugins.registry import build_registry_snapshot
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


class _FakeRecallProvider:
    """Small provider stub that returns a single stream delta."""

    def stream(self, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        async def _events() -> AsyncIterator[dict[str, object]]:
            yield {"type": "delta", "content": "NONE"}

        return _events()


def test_bundled_active_recall_manifest_builds_provider_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active Recall is a bundled default context provider."""
    monkeypatch.setenv("PAWRRTAL_HOME", str(tmp_path / "home"))

    providers = build_turn_context_providers(workspace_root=tmp_path)

    active_recall = next(
        provider for provider in providers if provider.plugin_id == "active_recall"
    )
    assert active_recall.capability_id == "active_recall"
    assert active_recall.timeout_seconds == 10
    assert active_recall.provider.__name__ == "run_active_recall"


def test_active_recall_resolves_provider_with_workspace_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recall sub-agent uses workspace-scoped provider credentials."""
    seen: dict[str, object] = {}

    def _resolve_llm(model_id: str, **kwargs: object) -> _FakeRecallProvider:
        seen["model_id"] = model_id
        seen["workspace_root"] = kwargs.get("workspace_root")
        return _FakeRecallProvider()

    monkeypatch.setattr("app.turns.pipeline.subcalls.resolve_llm", _resolve_llm)
    ctx = TurnContextProviderContext(
        conversation_id=uuid4(),
        user_id=uuid4(),
        question="What do we know?",
        workspace_root=tmp_path,
    )

    result = asyncio.run(
        recall_agent._run_recall_stream(
            ctx,
            "google-ai:google/gemini-3.1-flash-lite",
            "",
            False,
        )
    )

    assert seen == {
        "model_id": "google-ai:google/gemini-3.1-flash-lite",
        "workspace_root": tmp_path,
    }
    assert result[0] == "NONE"


@pytest.mark.anyio
async def test_active_recall_draft_updates_are_transport_neutral() -> None:
    """Active Recall emits plain draft text; channels own presentation formatting."""
    updates: list[str] = []

    async def _events() -> AsyncIterator[dict[str, object]]:
        yield {"type": "tool_use", "name": "lcm_search"}
        yield {"type": "delta", "content": "**memory** <raw>"}

    async def _draft_updater(text: str) -> None:
        updates.append(text)

    result = await recall_agent._collect_stream_telemetry(
        _events(),
        draft_updater=_draft_updater,
    )

    assert result[0] == "**memory** <raw>"
    assert updates[0] == "Recalling memory..."
    assert any("lcm_search()" in update for update in updates)
    assert any("**memory** <raw>" in update for update in updates)
    assert all("<b>" not in update for update in updates)
    assert all("<i>" not in update for update in updates)


def test_turn_context_provider_hot_reload_respects_workspace_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace state can disable a bundled provider on the next reload."""
    monkeypatch.setenv("PAWRRTAL_HOME", str(tmp_path / "home"))
    assert any(
        provider.plugin_id == "active_recall"
        for provider in build_turn_context_providers(workspace_root=tmp_path)
    )
    save_plugin_state(
        plugin_state_path(
            plugin_id="active_recall",
            scope="workspace",
            workspace_root=tmp_path,
        ),
        PluginState(enabled=False),
    )

    providers = build_turn_context_providers(workspace_root=tmp_path)

    assert all(provider.plugin_id != "active_recall" for provider in providers)


def test_workspace_plugins_cannot_register_turn_context_provider(tmp_path: Path) -> None:
    """Workspace plugins cannot load trusted Python lifecycle adapters."""
    plugin_dir = tmp_path / ".agent" / "plugins" / "workspace_recall"
    plugin_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "id": "workspace_recall",
        "name": "Workspace Recall",
        "description": "Workspace plugin that should not load trusted Python.",
        "version": "1.0.0",
        "enabled_by_default": True,
        "capabilities": [
            {
                "type": "turn_context_provider",
                "id": "workspace_recall",
                "title": "Workspace Recall",
                "description": "Attempt to provide trusted Python context from a workspace.",
                "entrypoint": "workspace_recall.provider:run",
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    discovered = discover_plugins((PluginRoot("workspace", tmp_path / ".agent" / "plugins"),))

    snapshot = build_registry_snapshot(discovered, workspace_root=tmp_path)

    assert snapshot.outcomes[0].status == "failed"
    assert snapshot.outcomes[0].reason
