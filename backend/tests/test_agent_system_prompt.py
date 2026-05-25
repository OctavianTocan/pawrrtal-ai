"""Tests for the shared Paw system prompt."""

from __future__ import annotations

from pathlib import Path

from app.channels.turn_runner import _workspace_system_prompt
from app.core.agent_loop import (
    DEFAULT_AGENT_SYSTEM_PROMPT,
    PAW_CORE_SYSTEM_PROMPT,
    compose_agent_system_prompt,
)


def test_default_prompt_identifies_the_agent_as_a_paw() -> None:
    """Provider fallbacks still carry the Paw concept."""
    assert "user's Paw" in DEFAULT_AGENT_SYSTEM_PROMPT
    assert "Pawrrtal" in DEFAULT_AGENT_SYSTEM_PROMPT


def test_compose_agent_system_prompt_prepends_paw_identity() -> None:
    """Workspace identity layers sit below the durable Paw concept."""
    prompt = compose_agent_system_prompt("workspace identity")

    assert prompt.startswith(PAW_CORE_SYSTEM_PROMPT)
    assert "workspace identity" in prompt


def test_workspace_system_prompt_backfills_bootstrap_for_placeholder_identity(
    tmp_path: Path,
) -> None:
    """Untouched existing workspaces get first-run bootstrap instructions."""
    (tmp_path / "IDENTITY.md").write_text("_(set a name for your agent)_", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("operating rules", encoding="utf-8")

    prompt = _workspace_system_prompt(tmp_path)

    assert prompt is not None
    assert "user's Paw" in prompt
    assert "First-Run Paw Setup" in prompt
    assert (tmp_path / "BOOTSTRAP.md").exists()


def test_workspace_system_prompt_uses_default_without_workspace() -> None:
    """No-workspace turns still get the provider-neutral Paw prompt."""
    assert _workspace_system_prompt(None) == DEFAULT_AGENT_SYSTEM_PROMPT
