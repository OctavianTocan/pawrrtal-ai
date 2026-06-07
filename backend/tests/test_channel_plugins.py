"""Tests for manifest-backed channel registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.channels import registered_surfaces, resolve_channel
from app.channels.google_chat.channel import SURFACE_GOOGLE_CHAT, GoogleChatChannel
from app.channels.sse import SURFACE_ELECTRON, SURFACE_WEB, SSEChannel
from app.channels.telegram.channel import SURFACE_TELEGRAM, TelegramChannel
from app.plugins.state import PluginState, plugin_state_path, save_plugin_state


def test_core_channels_manifest_registers_runtime_channels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAWRRTAL_HOME", str(tmp_path / "home"))

    surfaces = set(registered_surfaces())

    assert {SURFACE_WEB, SURFACE_ELECTRON, SURFACE_TELEGRAM, SURFACE_GOOGLE_CHAT} <= surfaces
    assert isinstance(resolve_channel(SURFACE_WEB), SSEChannel)
    assert isinstance(resolve_channel(SURFACE_ELECTRON), SSEChannel)
    assert isinstance(resolve_channel(SURFACE_TELEGRAM), TelegramChannel)
    assert isinstance(resolve_channel(SURFACE_GOOGLE_CHAT), GoogleChatChannel)


def test_disabled_core_channel_plugin_falls_back_to_web(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pawrrtal_home = tmp_path / "home"
    monkeypatch.setenv("PAWRRTAL_HOME", str(pawrrtal_home))
    save_plugin_state(
        plugin_state_path(
            plugin_id="core_channels",
            scope="global",
            pawrrtal_home=pawrrtal_home,
        ),
        PluginState(enabled=False),
    )

    surfaces = registered_surfaces()

    assert surfaces == [SURFACE_WEB]
    assert resolve_channel(SURFACE_TELEGRAM).surface == SURFACE_WEB
