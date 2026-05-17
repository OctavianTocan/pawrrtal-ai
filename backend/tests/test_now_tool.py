"""Tests for the ``now`` AgentTool (#294)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.tools.now import make_now_tool  # noqa: E402

pytestmark = pytest.mark.anyio


async def test_now_returns_utc_with_no_args() -> None:
    tool = make_now_tool()
    result = await tool.execute("call-1")
    assert "UTC now:" in result
    assert "Timezone: UTC" in result
    assert "Day of week:" in result


async def test_now_uses_default_timezone_when_unset() -> None:
    tool = make_now_tool(default_timezone="Europe/Madrid")
    result = await tool.execute("call-1")
    assert "Timezone: Europe/Madrid" in result


async def test_now_honours_explicit_tz_argument() -> None:
    tool = make_now_tool()
    result = await tool.execute("call-1", tz="America/Los_Angeles")
    assert "Timezone: America/Los_Angeles" in result


async def test_now_falls_back_to_utc_on_unknown_timezone() -> None:
    tool = make_now_tool()
    result = await tool.execute("call-1", tz="Nowhere/Imaginary")
    assert "Timezone: UTC" in result
    # The fallback must explain itself so the model can suggest a
    # correction next turn rather than silently accepting nonsense input.
    assert "fell back to UTC" in result


async def test_now_treats_blank_tz_like_missing() -> None:
    tool = make_now_tool(default_timezone="UTC")
    result = await tool.execute("call-1", tz="   ")
    assert "Timezone: UTC" in result
    # Specifically: no "fell back" note — blank input is treated as
    # "no input", which falls through to the default timezone path.
    assert "fell back" not in result


async def test_now_metadata_exposes_optional_tz_parameter() -> None:
    tool = make_now_tool()
    assert tool.name == "now"
    assert "tz" in tool.parameters["properties"]
    # The parameter must be optional — issue #294 specifies tz defaults
    # to the user's configured timezone (or UTC).
    assert "tz" not in tool.parameters.get("required", [])
