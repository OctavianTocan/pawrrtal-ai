"""Tests for plugin-declared process lifespans."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI

from app.infrastructure.startup import plugin_lifespans
from app.plugins.manifest import PluginManifest
from app.plugins.registry import ContributionRegistrySnapshot, PluginLoadOutcome
from app.plugins.state import PluginState

pytestmark = pytest.mark.anyio

_EVENTS: list[str] = []


@asynccontextmanager
async def _fake_channel_lifespan() -> AsyncIterator[Any]:
    _EVENTS.append("enter")
    try:
        yield SimpleNamespace(bot="fake-bot")
    finally:
        _EVENTS.append("exit")


async def _fake_post_start(app: FastAPI, service: Any) -> None:
    _EVENTS.append(f"post:{service.bot}")
    app.state.post_started_with = service.bot


async def test_reload_plugin_lifespans_enters_and_stops_channel_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plugin lifecycle metadata controls startup and shutdown."""
    _EVENTS.clear()
    app = FastAPI()
    monkeypatch.setattr(plugin_lifespans, "_reload_plugins", _fake_snapshot)
    monkeypatch.setattr(plugin_lifespans, "_load_callable", _fake_load_callable)

    await plugin_lifespans.reload_plugin_lifespans(app)

    assert app.state.test_service.bot == "fake-bot"
    assert app.state.post_started_with == "fake-bot"
    assert _EVENTS == ["enter", "post:fake-bot"]

    await plugin_lifespans.stop_plugin_lifespans(app)

    assert _EVENTS == ["enter", "post:fake-bot", "exit"]


def _fake_load_callable(entrypoint: str) -> Any:
    return {
        "test:lifespan": _fake_channel_lifespan,
        "test:post_start": _fake_post_start,
    }[entrypoint]


def _fake_snapshot() -> ContributionRegistrySnapshot:
    manifest = PluginManifest.model_validate(
        {
            "schema_version": 1,
            "id": "test_channel_plugin",
            "name": "Test Channel Plugin",
            "description": "Test channel plugin with a declared process lifespan.",
            "version": "1.0.0",
            "enabled_by_default": True,
            "capabilities": [
                {
                    "type": "channel",
                    "id": "test_channel",
                    "title": "Test Channel",
                    "description": "Test channel with startup and shutdown hooks.",
                    "surface": "test",
                    "entrypoint": "app.channels.plugin_adapters:make_sse_channel",
                    "lifespan": {
                        "entrypoint": "test:lifespan",
                        "context_key": "test_lifespan_context",
                        "service_key": "test_service",
                        "post_start": "test:post_start",
                        "order": 1,
                    },
                }
            ],
        }
    )
    outcome = PluginLoadOutcome(
        plugin_id=manifest.id,
        source_type="bundled",
        manifest_path=Path("/tmp/test-channel-plugin/plugin.json"),
        status="active",
        reason=None,
        fingerprint="test",
        state=PluginState(enabled=True),
        manifest=manifest,
    )
    return ContributionRegistrySnapshot(
        workspace_key="global",
        outcomes=(outcome,),
        capabilities=(),
        fingerprint="test",
    )
