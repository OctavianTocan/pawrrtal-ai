"""Tests for ``app.core.runtime_context``.

Per-turn system-prompt block covering current time (#294), active model
(#309), iteration budget (#291), and tool inventory (#289).
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.agent_loop.types import AgentSafetyConfig, AgentTool  # noqa: E402
from app.core.runtime_context import (  # noqa: E402
    ProviderIdentity,
    append_runtime_context,
    compose_current_time_block,
    compose_resource_budget_block,
    compose_runtime_context_block,
    compose_runtime_identity_block,
    compose_tool_inventory_block,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now() -> _dt.datetime:
    """Deterministic UTC instant used across tests."""
    return _dt.datetime(2026, 5, 17, 23, 9, 42, tzinfo=_dt.UTC)


def _make_tool(name: str, description: str) -> AgentTool:
    async def _execute(tool_call_id: str, **_: object) -> str:
        return ""

    return AgentTool(
        name=name,
        description=description,
        parameters={"type": "object", "properties": {}},
        execute=_execute,
    )


# ---------------------------------------------------------------------------
# compose_current_time_block (#294)
# ---------------------------------------------------------------------------


def test_current_time_block_renders_utc_iso_and_weekday(fixed_now: _dt.datetime) -> None:
    block = compose_current_time_block(fixed_now)
    assert block.startswith("## Current time")
    assert "UTC now: 2026-05-17T23:09:42Z" in block
    # The fixed date is a Sunday — block must surface day-of-week so
    # the model can answer "what day is it?" without a tool call.
    assert "Sunday" in block


def test_current_time_block_uses_now_when_no_override() -> None:
    block = compose_current_time_block()
    # Defensive check: the block should always be non-empty regardless
    # of the clock — the function never returns an empty string.
    assert block.startswith("## Current time")


# ---------------------------------------------------------------------------
# compose_runtime_identity_block (#309)
# ---------------------------------------------------------------------------


def test_identity_block_omits_when_no_identity() -> None:
    assert compose_runtime_identity_block(None) is None


def test_identity_block_omits_when_model_id_empty() -> None:
    identity = ProviderIdentity(provider="anthropic", model_id="")
    assert compose_runtime_identity_block(identity) is None


def test_identity_block_renders_provider_and_model() -> None:
    identity = ProviderIdentity(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
    )
    block = compose_runtime_identity_block(identity)
    assert block is not None
    assert "Provider: anthropic" in block
    assert "Model id: claude-sonnet-4-6" in block
    assert "Display name: Claude Sonnet 4.6" in block
    # Trust note must be present so the model knows to prefer the
    # injected metadata over training-data identity claims.
    assert "trust it" in block


def test_identity_block_skips_display_when_equal_to_model_id() -> None:
    identity = ProviderIdentity(
        provider="google-ai",
        model_id="gemini-3-flash-preview",
        display_name="gemini-3-flash-preview",
    )
    block = compose_runtime_identity_block(identity)
    assert block is not None
    assert "Display name" not in block


def test_identity_block_renders_reasoning_effort_when_set() -> None:
    """Reasoning effort surfaces in the active-model block when present."""
    identity = ProviderIdentity(
        provider="anthropic",
        model_id="claude-opus-4-7",
        display_name="Claude Opus 4.7",
        reasoning_effort="high",
    )
    block = compose_runtime_identity_block(identity)
    assert block is not None
    assert "Reasoning effort: high" in block


def test_identity_block_omits_reasoning_when_none() -> None:
    """Models running without a knob don't get a misleading 'default' line."""
    identity = ProviderIdentity(
        provider="anthropic",
        model_id="claude-opus-4-7",
        display_name="Claude Opus 4.7",
        reasoning_effort=None,
    )
    block = compose_runtime_identity_block(identity)
    assert block is not None
    assert "Reasoning effort" not in block


# ---------------------------------------------------------------------------
# compose_resource_budget_block (#291)
# ---------------------------------------------------------------------------


def test_resource_budget_block_omits_when_safety_is_none() -> None:
    assert compose_resource_budget_block(None) is None


def test_resource_budget_block_renders_finite_caps() -> None:
    block = compose_resource_budget_block(
        AgentSafetyConfig(max_iterations=12, max_wall_clock_seconds=180.0)
    )
    assert block is not None
    assert "12 tool-using iterations" in block
    assert "180 seconds of wall-clock time" in block


def test_resource_budget_block_renders_unlimited_when_disabled() -> None:
    block = compose_resource_budget_block(
        AgentSafetyConfig(max_iterations=None, max_wall_clock_seconds=None)
    )
    assert block is not None
    assert "unlimited tool-using iterations" in block
    assert "unlimited wall-clock time" in block


# ---------------------------------------------------------------------------
# compose_tool_inventory_block (#289)
# ---------------------------------------------------------------------------


def test_tool_inventory_omitted_when_inventory_is_none() -> None:
    assert compose_tool_inventory_block(None) is None


def test_tool_inventory_renders_empty_with_explicit_no_tools_line() -> None:
    block = compose_tool_inventory_block([])
    assert block is not None
    assert "No tools are bound" in block
    # The empty inventory must steer the model away from filesystem
    # discovery — that's the entire reason the section exists (#289).
    assert "Do not attempt filesystem discovery" in block


def test_tool_inventory_lists_each_tool_with_first_sentence() -> None:
    tools = [
        _make_tool(
            "read_file",
            "Read a file from the workspace. Supports text and Markdown.",
        ),
        _make_tool(
            "now",
            "Return the current time as ISO-8601 UTC plus the user's local "
            "time. Use this when you need to reason about today/yesterday.",
        ),
    ]
    block = compose_tool_inventory_block(tools)
    assert block is not None
    assert "`read_file`" in block
    assert "Read a file from the workspace." in block
    # Second sentence of the description must not leak through — the
    # truncation is what keeps the block scannable.
    assert "Supports text and Markdown" not in block
    assert "`now`" in block


# ---------------------------------------------------------------------------
# compose_runtime_context_block + append_runtime_context
# ---------------------------------------------------------------------------


def test_full_block_includes_every_supplied_section(fixed_now: _dt.datetime) -> None:
    block = compose_runtime_context_block(
        identity=ProviderIdentity(provider="anthropic", model_id="claude-opus-4-7"),
        safety=AgentSafetyConfig(max_iterations=25, max_wall_clock_seconds=300.0),
        tools=[_make_tool("read_file", "Read a file.")],
        now=fixed_now,
    )
    assert "## Current time" in block
    assert "## Active model" in block
    assert "## Resource budget for this turn" in block
    assert "## Tools available this turn" in block


def test_full_block_time_only_when_others_missing(fixed_now: _dt.datetime) -> None:
    block = compose_runtime_context_block(now=fixed_now)
    assert block.startswith("## Current time")
    # No optional sections should leak in.
    assert "## Active model" not in block
    assert "## Resource budget" not in block
    assert "## Tools available" not in block


def test_append_runtime_context_passes_none_through() -> None:
    """A ``None`` base prompt stays ``None`` — providers use their default."""
    assert append_runtime_context(None) is None


def test_append_runtime_context_appends_with_blank_line(fixed_now: _dt.datetime) -> None:
    base = "Existing system prompt."
    result = append_runtime_context(base, now=fixed_now)
    assert result is not None
    assert result.startswith(base)
    # Blank line separator so the runtime block reads as a distinct
    # trailing section, not an accidental continuation of the prompt.
    assert "\n\n## Current time" in result
