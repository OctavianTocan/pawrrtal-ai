"""Tests for manifest-backed provider plugins."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest

from app.plugins.state import PluginState, plugin_state_path, save_plugin_state
from app.providers.base import StreamEvent
from app.providers.factory import resolve_llm
from app.providers.plugin_provider import (
    ProviderFactoryContext,
    parse_plugin_model_id,
    provider_model_entries,
)
from app.schemas import ChatRequest


class _FakePluginLLM:
    """Small provider returned by the fake provider plugin factory."""

    def __init__(self, model_id: str, workspace_root: Path | None) -> None:
        self.model_id = model_id
        self.workspace_root = workspace_root

    def stream(self, *_args: Any, **_kwargs: Any) -> AsyncIterator[StreamEvent]:
        return self._empty()

    async def _empty(self) -> AsyncIterator[StreamEvent]:
        if False:
            yield {"type": "done"}


def make_fake_provider(ctx: ProviderFactoryContext) -> _FakePluginLLM:
    """Entrypoint used by the fake provider plugin manifest."""
    return _FakePluginLLM(ctx.model_id.id, ctx.workspace_root)


def _write_provider_plugin(*, pawrrtal_home: Path, workspace_root: Path) -> None:
    """Write a global trusted provider plugin and enable it for a workspace."""
    plugin_dir = pawrrtal_home / "plugins" / "fake_provider"
    plugin_dir.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "id": "fake_provider",
        "name": "Fake Provider",
        "description": "Trusted provider plugin used by provider plugin tests.",
        "version": "1.0.0",
        "capabilities": [
            {
                "type": "provider",
                "id": "fake_provider",
                "title": "Fake Provider",
                "description": "Resolve fake models through a trusted provider plugin factory.",
                "entrypoint": "tests.test_provider_plugins:make_fake_provider",
                "models": [
                    {
                        "id": "fake_vendor/fake-model",
                        "name": "Fake Model",
                        "sort_order": 5,
                        "reasoning": ["low", "medium"],
                        "supports_images": True,
                        "supports_tools": True,
                    }
                ],
            }
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    save_plugin_state(
        plugin_state_path(
            plugin_id="fake_provider",
            scope="workspace",
            workspace_root=workspace_root,
        ),
        PluginState(enabled=True),
    )


def test_plugin_model_id_validator_accepts_dynamic_provider_ids() -> None:
    parsed = parse_plugin_model_id("fake_provider:fake_vendor/fake-model")

    assert parsed.id == "fake_provider:fake_vendor/fake-model"
    request = ChatRequest(
        question="hi",
        conversation_id=uuid.uuid4(),
        model_id=parsed.id,
    )
    assert request.model_id == parsed.id


def test_provider_model_entries_include_active_global_provider_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pawrrtal_home = tmp_path / "home"
    workspace_root = tmp_path / "workspace"
    monkeypatch.setenv("PAWRRTAL_HOME", str(pawrrtal_home))
    _write_provider_plugin(pawrrtal_home=pawrrtal_home, workspace_root=workspace_root)

    entries = provider_model_entries(workspace_root=workspace_root)

    entry = next(model for model in entries if model.plugin_id == "fake_provider")
    assert entry.id == "fake_provider:fake_vendor/fake-model"
    assert entry.display_name == "Fake Model"
    assert entry.supports_reasoning == ("low", "medium")
    assert entry.supports_images is True


def test_resolve_llm_uses_provider_plugin_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pawrrtal_home = tmp_path / "home"
    workspace_root = tmp_path / "workspace"
    monkeypatch.setenv("PAWRRTAL_HOME", str(pawrrtal_home))
    _write_provider_plugin(pawrrtal_home=pawrrtal_home, workspace_root=workspace_root)

    provider = resolve_llm(
        "fake_provider:fake_vendor/fake-model",
        workspace_root=workspace_root,
    )

    assert provider.__class__.__name__ == "_FakePluginLLM"
    provider_obj = cast(Any, provider)
    assert provider_obj.model_id == "fake_provider:fake_vendor/fake-model"
    assert provider_obj.workspace_root == workspace_root
