"""Shared fixtures for paw CLI tests."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Isolate every paw test from the developer's real ~/.config/pawrrtal."""
    monkeypatch.setenv("PAW_CONFIG_DIR", str(tmp_path))
