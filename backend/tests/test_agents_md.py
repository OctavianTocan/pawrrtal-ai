"""Tests for the agents_md workspace prompt assembler."""

from __future__ import annotations

from pathlib import Path

from app.core.persona_bootstrap import IDENTITY_BEGIN, IDENTITY_END
from app.core.tools.agents_md import (
    PROTECTED_FILENAMES,
    assemble_workspace_prompt,
    read_skills_index,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _write_identity_block(workspace_root: Path, *, completed: bool) -> None:
    """Write a PREFERENCES.md with the identity JSON block in the expected state."""
    prefs = workspace_root / ".agent" / "memory" / "personal" / "PREFERENCES.md"
    prefs.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        '{"name": "Paw", "vibe": "balanced", "emoji": null, '
        f'"bootstrap_completed": {"true" if completed else "false"}}}'
    )
    prefs.write_text(
        f"# Preferences\n\n{IDENTITY_BEGIN}\n{payload}\n{IDENTITY_END}\n",
        encoding="utf-8",
    )


class TestAssembleWorkspacePrompt:
    def test_includes_skills_index_when_present(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "AGENTS.md", "# AGENTS\n")
        _write(
            tmp_path / ".agent" / "skills" / "_index.md",
            "# Skill Map\n\nsome skills\n",
        )

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "Skill Map" in result
        assert "some skills" in result

    def test_returns_agents_md_when_only_one_present(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "AGENTS.md", "# AGENTS\n")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "AGENTS" in result

    def test_returns_none_when_all_sources_missing(self, tmp_path: Path) -> None:
        result = assemble_workspace_prompt(tmp_path)
        assert result is None

    def test_sections_joined_with_separator(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "AGENTS.md", "AGENTS_CONTENT")
        _write(tmp_path / ".agent" / "skills" / "_index.md", "INDEX_CONTENT")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        parts = result.split("\n\n---\n\n")
        assert parts == ["AGENTS_CONTENT", "INDEX_CONTENT"]

    def test_includes_bootstrap_skill_while_identity_pending(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "AGENTS.md", "AGENTS_CONTENT")
        _write(
            tmp_path / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md",
            "BOOTSTRAP_SKILL_BODY",
        )
        _write_identity_block(tmp_path, completed=False)

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        parts = result.split("\n\n---\n\n")
        assert parts == ["AGENTS_CONTENT", "BOOTSTRAP_SKILL_BODY"]

    def test_omits_bootstrap_after_identity_completed(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "AGENTS.md", "AGENTS_CONTENT")
        _write(
            tmp_path / ".agent" / "skills" / "paw-bootstrap" / "SKILL.md",
            "BOOTSTRAP_SKILL_BODY",
        )
        _write_identity_block(tmp_path, completed=True)

        result = assemble_workspace_prompt(tmp_path)

        assert result == "AGENTS_CONTENT"

    def test_skills_index_alone_returns_non_none(self, tmp_path: Path) -> None:
        _write(tmp_path / ".agent" / "skills" / "_index.md", "# Index\n")

        result = assemble_workspace_prompt(tmp_path)

        assert result is not None
        assert "Index" in result


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
        assert ".agent/AGENTS.md" in PROTECTED_FILENAMES

    def test_old_root_files_are_no_longer_listed(self) -> None:
        for legacy in ("SOUL.md", "IDENTITY.md", "USER.md", "BOOTSTRAP.md"):
            assert legacy not in PROTECTED_FILENAMES
