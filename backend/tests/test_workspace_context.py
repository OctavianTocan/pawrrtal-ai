"""Tests for ``app.core.governance.workspace_context``.

The loader reads root context files plus the workspace's internal
``.agent/`` skills/protocols tree and produces a single struct. These
tests exercise every combination of present / missing files and confirm
the system prompt + permissions roll up correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.core.governance.workspace_context import (
    SettingsPermissions,
    load_workspace_context,
)
from app.core.persona_bootstrap import IDENTITY_BEGIN, IDENTITY_END


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _write_identity_block(workspace_root: Path, *, completed: bool) -> None:
    prefs = workspace_root / "PREFERENCES.md"
    payload = (
        '{"name": "Paw", "vibe": "balanced", "emoji": null, '
        f'"bootstrap_completed": {"true" if completed else "false"}}}'
    )
    prefs.write_text(
        f"# Preferences\n\n{IDENTITY_BEGIN}\n{payload}\n{IDENTITY_END}\n",
        encoding="utf-8",
    )


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

    def test_skills_index_appended_after_agents(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "operating rules")
        _write(tmp_path / ".agent" / "skills" / "_index.md", "skill catalogue")
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "operating rules" in ctx.system_prompt
        assert "skill catalogue" in ctx.system_prompt

    def test_root_context_files_are_loaded(self, tmp_path: Path) -> None:
        _write(tmp_path / "SOUL.md", "soul")
        _write(tmp_path / "AGENTS.md", "rules")
        _write(tmp_path / "USER.md", "user")
        _write(tmp_path / "PREFERENCES.md", "prefs")

        ctx = load_workspace_context(tmp_path)

        assert ctx.system_prompt == "soul\n\n---\n\nrules\n\n---\n\nuser\n\n---\n\nprefs"
        assert {path.name for path in ctx.loaded_from} == {
            "SOUL.md",
            "AGENTS.md",
            "USER.md",
            "PREFERENCES.md",
        }

    def test_loaded_from_omits_empty_root_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "rules")
        _write(tmp_path / "PREFERENCES.md", "")

        ctx = load_workspace_context(tmp_path)

        assert ctx.system_prompt == "rules"
        assert [path.name for path in ctx.loaded_from] == ["AGENTS.md"]

    def test_bootstrap_injected_while_identity_pending(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "operating rules")
        _write(
            tmp_path / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md",
            "first-run setup body",
        )
        _write_identity_block(tmp_path, completed=False)
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        assert "first-run setup body" in ctx.system_prompt

    def test_bootstrap_injection_suppressed_after_identity_completed(self, tmp_path: Path) -> None:
        """When bootstrap is done, the bootstrap body must not be force-
        injected ahead of the skill catalogue. (It still appears inside
        the catalogue because every skill body lands there.)
        """
        _write(tmp_path / "AGENTS.md", "operating rules")
        _write(
            tmp_path / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md",
            "first-run setup body",
        )
        _write_identity_block(tmp_path, completed=True)
        ctx = load_workspace_context(tmp_path)
        assert ctx.system_prompt is not None
        pre_catalogue, _, _ = ctx.system_prompt.partition("## Available Skills")
        assert "first-run setup body" not in pre_catalogue


class TestSkillsCatalogue:
    def test_no_skills_dir(self, tmp_path: Path) -> None:
        ctx = load_workspace_context(tmp_path)
        assert ctx.skills == ()

    def test_one_skill_appears_in_prompt(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".agent" / "skills" / "summarize" / "SKILL.md",
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
        (tmp_path / ".agent" / "skills" / "noop").mkdir(parents=True)
        ctx = load_workspace_context(tmp_path)
        assert ctx.skills == ()


class TestPermissions:
    """The Markdown permissions file is appended as conversational context.

    A future PR will land a Markdown→allowlist parser; until then the
    mechanical gate stays permissive.
    """

    def test_no_permissions_file(self, tmp_path: Path) -> None:
        ctx = load_workspace_context(tmp_path)
        assert ctx.permissions == SettingsPermissions()
        assert ctx.enabled_tools is None

    def test_permissions_md_present_is_recorded_but_does_not_gate(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".agent" / "protocols" / "permissions.md",
            "# Permissions\n\n## Never allowed\n- Bash(rm -rf /)\n",
        )
        ctx = load_workspace_context(tmp_path)
        # Permissions stay empty (no Markdown parser yet), but the
        # content is still included in the prompt for the agent to honor
        # conversationally.
        assert ctx.permissions == SettingsPermissions()
        assert ctx.enabled_tools is None
        assert ctx.system_prompt == (
            "## Workspace Permissions\n\n# Permissions\n\n## Never allowed\n- Bash(rm -rf /)"
        )
        loaded_paths = {str(p) for p in ctx.loaded_from}
        assert any("protocols/permissions.md" in p for p in loaded_paths)
