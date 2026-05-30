"""Tests for the agents_md workspace prompt assembler."""

from __future__ import annotations

from pathlib import Path

from app.tools.agents_md import (
    PROTECTED_FILENAMES,
    assemble_workspace_prompt,
    read_skills_index,
)
from app.workspace.persona_bootstrap import IDENTITY_BEGIN, IDENTITY_END


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _write_identity_block(workspace_root: Path, *, completed: bool) -> None:
    """Write a PREFERENCES.md with the identity JSON block in the expected state."""
    prefs = workspace_root / "PREFERENCES.md"
    prefs.write_text(_identity_block_text(completed=completed), encoding="utf-8")


def _identity_block_text(*, completed: bool) -> str:
    payload = (
        '{"name": "Paw", "vibe": "balanced", "emoji": null, '
        f'"bootstrap_completed": {"true" if completed else "false"}}}'
    )
    return f"# Preferences\n\n{IDENTITY_BEGIN}\n{payload}\n{IDENTITY_END}"


class TestAssembleWorkspacePrompt:
    def test_includes_skills_index_when_present(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "# AGENTS\n")
        _write(
            tmp_path / ".agent" / "skills" / "_index.md",
            "# Skill Map\n\nsome skills\n",
        )

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "Skill Map" in result
        assert "some skills" in result

    def test_returns_agents_md_when_only_one_present(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "# AGENTS\n")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "AGENTS" in result

    def test_returns_none_when_all_sources_missing(self, tmp_path: Path) -> None:
        result = assemble_workspace_prompt(tmp_path)
        assert result is None

    def test_sections_joined_with_separator(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "AGENTS_CONTENT")
        _write(tmp_path / ".agent" / "skills" / "_index.md", "INDEX_CONTENT")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        parts = result.split("\n\n---\n\n")
        assert parts == ["AGENTS_CONTENT", "INDEX_CONTENT"]

    def test_includes_bootstrap_skill_while_identity_pending(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "AGENTS_CONTENT")
        _write(
            tmp_path / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md",
            "BOOTSTRAP_SKILL_BODY",
        )
        _write_identity_block(tmp_path, completed=False)

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        parts = result.split("\n\n---\n\n")
        assert parts == [
            "AGENTS_CONTENT",
            _identity_block_text(completed=False),
            "BOOTSTRAP_SKILL_BODY",
        ]

    def test_omits_bootstrap_after_identity_completed(self, tmp_path: Path) -> None:
        _write(tmp_path / "AGENTS.md", "AGENTS_CONTENT")
        _write(
            tmp_path / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md",
            "BOOTSTRAP_SKILL_BODY",
        )
        _write_identity_block(tmp_path, completed=True)

        result = assemble_workspace_prompt(tmp_path)

        assert result == "AGENTS_CONTENT\n\n---\n\n" + _identity_block_text(completed=True)

    def test_skills_index_alone_returns_non_none(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "skills" / "_index.md", "# Index\n")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "Index" in result

    def test_root_context_files_are_loaded_in_order(self, tmp_path: Path) -> None:
        _write(tmp_path / "SOUL.md", "SOUL_CONTENT")
        _write(tmp_path / "AGENTS.md", "AGENTS_CONTENT")
        _write(tmp_path / "USER.md", "USER_CONTENT")
        _write(tmp_path / "PREFERENCES.md", "PREFERENCES_CONTENT")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert result.split("\n\n---\n\n") == [
            "SOUL_CONTENT",
            "AGENTS_CONTENT",
            "USER_CONTENT",
            "PREFERENCES_CONTENT",
        ]


class TestReadSkillsIndex:
    def test_returns_content_when_present(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "skills" / "_index.md", "hello index")
        assert read_skills_index(tmp_path) == "hello index"

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert read_skills_index(tmp_path) is None


class TestProtectedFilenames:
    def test_skills_index_is_protected(self) -> None:
        assert ".agent/skills/_index.md" in PROTECTED_FILENAMES

    def test_agents_md_is_protected(self) -> None:
        assert "AGENTS.md" in PROTECTED_FILENAMES

    def test_user_editable_root_files_are_not_protected(self) -> None:
        for filename in ("SOUL.md", "USER.md", "PREFERENCES.md", "HEARTBEAT.md"):
            assert filename not in PROTECTED_FILENAMES
