"""Tests for the shared Paw system prompt."""

from __future__ import annotations

from pathlib import Path

from app.channels.turn_runner import _workspace_system_prompt
from app.core.agent_system_prompt import (
    DEFAULT_AGENT_SYSTEM_PROMPT,
    PAW_CORE_SYSTEM_PROMPT,
    compose_agent_system_prompt,
)
from app.core.persona_bootstrap import IDENTITY_BEGIN, IDENTITY_END


def test_default_prompt_identifies_the_agent_as_a_paw() -> None:
    """Provider fallbacks still carry the Paw concept."""
    assert "user's Paw" in DEFAULT_AGENT_SYSTEM_PROMPT
    assert "Pawrrtal" in DEFAULT_AGENT_SYSTEM_PROMPT


def test_compose_agent_system_prompt_prepends_paw_identity() -> None:
    """Workspace identity layers sit below the durable Paw concept."""
    prompt = compose_agent_system_prompt("workspace identity")

    assert prompt.startswith(PAW_CORE_SYSTEM_PROMPT)
    assert "workspace identity" in prompt


def test_workspace_system_prompt_includes_bootstrap_when_identity_pending(
    tmp_path: Path,
) -> None:
    """Workspaces with bootstrap_completed=false get the bootstrap skill body."""
    (tmp_path / "AGENTS.md").write_text("operating rules", encoding="utf-8")
    prefs = tmp_path / "PREFERENCES.md"
    prefs.write_text(
        f"# Prefs\n\n{IDENTITY_BEGIN}\n"
        '{"name": null, "vibe": null, "emoji": null, "bootstrap_completed": false}'
        f"\n{IDENTITY_END}\n",
        encoding="utf-8",
    )
    bootstrap = tmp_path / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text("FIRST_RUN_SETUP_BODY", encoding="utf-8")

    prompt = _workspace_system_prompt(tmp_path)

    assert prompt is not None
    assert "user's Paw" in prompt
    assert "FIRST_RUN_SETUP_BODY" in prompt


def test_workspace_system_prompt_uses_default_without_workspace() -> None:
    """No-workspace turns still get the provider-neutral Paw prompt."""
    assert _workspace_system_prompt(None) == DEFAULT_AGENT_SYSTEM_PROMPT
