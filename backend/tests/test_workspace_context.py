"""Tests for ``app.core.governance.workspace_context``.

The loader walks the workspace and produces a single struct.  These
tests exercise the filesystem cases (every combination of present /
missing files) and confirm the system prompt + permissions roll up
correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.governance.workspace_context import (
    SettingsPermissions,
    load_workspace_context,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


class TestEmptyWorkspace:
    def test_no_files_yields_empty_context(self, tmp_path: Path) -> None:
        ctx = load_workspace_context(tmp_path)
        assert ctx.is_empty
        assert ctx.system_prompt is None
        assert ctx.enabled_tools is None
        assert ctx.skills == ()
        assert ctx.loaded_from == ()

    def test_loader_disabled_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Even with files present, the disabled flag short-circuits.
        _write(tmp_path / "AGENTS.md", "rules")
        monkeypatch.setattr(settings, "workspace_context_enabled", False)
        ctx = load_workspace_context(tmp_path)
        assert ctx.is_empty


class TestPromptAssembly:
    def test_agents_md_only(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "operating rules")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt == "operating rules"
        assert ctx.enabled_tools is None

    def test_soul_and_agents_concatenated(self, tmp_path: Path) -> None:
        _write(tmp_path / "SOUL.md", "I am the agent")
        _write(tmp_path / "AGENTS.md", "operating rules")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "I am the agent" in ctx.system_prompt
        assert "operating rules" in ctx.system_prompt
        # SOUL comes first.
        soul_pos = ctx.system_prompt.index("I am")
        agents_pos = ctx.system_prompt.index("operating")
        assert soul_pos < agents_pos

    def test_claude_md_appended(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "operating rules")
        _write(tmp_path / "CLAUDE.md", "claude code instructions")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "claude code instructions" in ctx.system_prompt

    def test_only_claude_md(self, tmp_path: Path) -> None:
        _write(tmp_path / "CLAUDE.md", "claude only")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "claude only" in ctx.system_prompt


class TestSkillsCatalogue:
    def test_no_skills_dir(self, tmp_path: Path) -> None:
        ctx = load_workspace_context(tmp_path)
        assert ctx.skills == ()

    def test_one_skill_appears_in_prompt(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".claude" / "skills" / "summarize" / "SKILL.md",
            "description: summarize a doc\n\nWhen the user asks…",
        )
        ctx = load_workspace_context(tmp_path)
        assert len(ctx.skills) == 1
        assert ctx.skills[0].name == "summarize"
        assert ctx.skills[0].description == "summarize a doc"
        assert ctx.system_prompt is not None
        assert "## Available Skills" in ctx.system_prompt
        assert "summarize" in ctx.system_prompt

    def test_skipped_skill_without_manifest(self, tmp_path: Path) -> None:
        # Empty directory under skills/ — no SKILL.md → skipped silently.
        (tmp_path / ".claude" / "skills" / "noop").mkdir(parents=True)
        ctx = load_workspace_context(tmp_path)
        assert ctx.skills == ()


class TestPermissions:
    def test_no_settings_file(self, tmp_path: Path) -> None:
        ctx = load_workspace_context(tmp_path)
        assert ctx.permissions == SettingsPermissions()
        assert ctx.enabled_tools is None

    def test_allow_only(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"permissions": {"allow": ["workspace_read", "exa_search"]}}),
        )
        ctx = load_workspace_context(tmp_path)
        assert ctx.permissions.allow == frozenset({"workspace_read", "exa_search"})
        assert ctx.enabled_tools == frozenset({"workspace_read", "exa_search"})

    def test_deny_subtracts_from_allow(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps(
                {
                    "permissions": {
                        "allow": ["workspace_read", "Bash"],
                        "deny": ["Bash"],
                    }
                }
            ),
        )
        ctx = load_workspace_context(tmp_path)
        assert ctx.enabled_tools == frozenset({"workspace_read"})

    def test_malformed_json_is_tolerated(self, tmp_path: Path) -> None:
        _write(tmp_path / ".claude" / "settings.json", "{not json")
        ctx = load_workspace_context(tmp_path)
        # Falls back to default-shaped permissions; doesn't raise.
        assert ctx.permissions == SettingsPermissions()
        assert ctx.enabled_tools is None

    def test_default_mode_captured(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"permissions": {"defaultMode": "ask"}}),
        )
        ctx = load_workspace_context(tmp_path)
        assert ctx.permissions.default_mode == "ask"

    def test_deny_only_returns_none_allowlist(self, tmp_path: Path) -> None:
        # Pure-deny semantics → still permissive (deny enforced separately
        # in a future PR; for now an empty allow falls through to None).
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"permissions": {"deny": ["Bash"]}}),
        )
        ctx = load_workspace_context(tmp_path)
        assert ctx.enabled_tools is None


class TestMemoryFilePromptWiring:
    """USER.md, IDENTITY.md, and MEMORY.md are loaded into the system prompt."""

    def test_user_md_appears_in_prompt_with_fill_header(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "rules")
        _write(tmp_path / "USER.md", "Name: Alice")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "Name: Alice" in ctx.system_prompt
        assert "## User" in ctx.system_prompt
        assert "1375" in ctx.system_prompt

    def test_memory_md_appears_in_prompt_with_fill_header(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "rules")
        _write(tmp_path / "MEMORY.md", "Prefers dark mode")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "Prefers dark mode" in ctx.system_prompt
        assert "## Memory" in ctx.system_prompt
        assert "2200" in ctx.system_prompt

    def test_identity_md_appears_after_base_prompt(self, tmp_path: Path) -> None:
        _write(tmp_path / "SOUL.md", "I am Paw")
        _write(tmp_path / "IDENTITY.md", "Friendly assistant")
        _write(tmp_path / "CLAUDE.md", "claude instructions")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "Friendly assistant" in ctx.system_prompt
        identity_pos = ctx.system_prompt.index("Friendly assistant")
        claude_pos = ctx.system_prompt.index("claude instructions")
        assert identity_pos < claude_pos

    def test_memory_files_appear_after_skills(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "rules")
        _write(
            tmp_path / ".claude" / "skills" / "search" / "SKILL.md",
            "description: search docs\n\nSearch body",
        )
        _write(tmp_path / "USER.md", "Name: Alice")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        skills_pos = ctx.system_prompt.index("## Available Skills")
        user_pos = ctx.system_prompt.index("## User")
        assert skills_pos < user_pos

    def test_missing_memory_files_omitted_gracefully(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "rules")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "## User" not in ctx.system_prompt
        assert "## Memory" not in ctx.system_prompt
        assert "## Identity" not in ctx.system_prompt
