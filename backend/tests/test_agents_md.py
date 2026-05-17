"""Tests for the agents_md workspace prompt assembler."""

from __future__ import annotations

from pathlib import Path

from app.core.persona_bootstrap import BOOTSTRAP_STATE_PATH
from app.core.tools.agents_md import (
    PROTECTED_FILENAMES,
    assemble_workspace_prompt,
    read_skills_index,
)


class TestAssembleWorkspacePrompt:
    def test_includes_skills_index_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "SOUL.md").write_text("# SOUL\n", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "_index.md").write_text("# Skill Map\n\nsome skills\n", encoding="utf-8")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "Skill Map" in result
        assert "some skills" in result

    def test_omits_skills_index_when_missing(self, tmp_path: Path) -> None:
        (tmp_path / "SOUL.md").write_text("# SOUL\n", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "SOUL" in result
        assert "AGENTS" in result

    def test_returns_none_when_all_three_missing(self, tmp_path: Path) -> None:
        result = assemble_workspace_prompt(tmp_path)
        assert result is None

    def test_sections_joined_with_separator(self, tmp_path: Path) -> None:
        (tmp_path / "SOUL.md").write_text("SOUL_CONTENT", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("AGENTS_CONTENT", encoding="utf-8")
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "_index.md").write_text("INDEX_CONTENT", encoding="utf-8")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        parts = result.split("\n\n---\n\n")
        assert len(parts) == 3
        assert parts[0] == "SOUL_CONTENT"
        assert parts[1] == "AGENTS_CONTENT"
        assert parts[2] == "INDEX_CONTENT"

    def test_includes_pending_bootstrap_after_agents(self, tmp_path: Path) -> None:
        (tmp_path / "SOUL.md").write_text("SOUL_CONTENT", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("AGENTS_CONTENT", encoding="utf-8")
        (tmp_path / "BOOTSTRAP.md").write_text("BOOTSTRAP_CONTENT", encoding="utf-8")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        parts = result.split("\n\n---\n\n")
        assert parts == ["SOUL_CONTENT", "AGENTS_CONTENT", "BOOTSTRAP_CONTENT"]

    def test_omits_bootstrap_after_completion_marker(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("AGENTS_CONTENT", encoding="utf-8")
        (tmp_path / "BOOTSTRAP.md").write_text("BOOTSTRAP_CONTENT", encoding="utf-8")
        state_path = tmp_path / BOOTSTRAP_STATE_PATH
        state_path.parent.mkdir()
        state_path.write_text('{"version": 1, "completed": true}', encoding="utf-8")

        result = assemble_workspace_prompt(tmp_path)

        assert result == "AGENTS_CONTENT"

    def test_skills_index_only_returns_non_none(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "_index.md").write_text("# Index\n", encoding="utf-8")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "Index" in result


class TestReadSkillsIndex:
    def test_returns_content_when_present(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "_index.md").write_text("hello index", encoding="utf-8")

        result = read_skills_index(tmp_path)
        assert result == "hello index"

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        result = read_skills_index(tmp_path)
        assert result is None


class TestProtectedFilenames:
    def test_skills_index_is_protected(self) -> None:
        assert "skills/_index.md" in PROTECTED_FILENAMES

    def test_agents_md_is_protected(self) -> None:
        assert "AGENTS.md" in PROTECTED_FILENAMES

    def test_soul_md_is_protected(self) -> None:
        assert "SOUL.md" in PROTECTED_FILENAMES
