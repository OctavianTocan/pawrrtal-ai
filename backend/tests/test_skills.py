"""Tests for the skills manifest reader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.config import settings
from app.tools.skills import read_skill_manifest


def _make_skill_dir(skills_dir: Path, name: str, with_skill_md: bool = True) -> Path:
    """Create a skill subdirectory, optionally with SKILL.md."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if with_skill_md:
        (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    return skill_dir


def _write_manifest(skills_dir: Path, entries: list[dict[str, Any]]) -> None:
    """Write JSONL entries to _manifest.jsonl."""
    lines = "\n".join(json.dumps(e) for e in entries)
    (skills_dir / "_manifest.jsonl").write_text(lines, encoding="utf-8")


class TestReadSkillManifest:
    def test_returns_empty_when_skills_dir_absent(self, tmp_path: Path) -> None:
        result = read_skill_manifest(tmp_path)
        assert result == []

    def test_empty_manifest_and_no_subdirs_returns_empty(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "_manifest.jsonl").write_text("", encoding="utf-8")

        result = read_skill_manifest(tmp_path)
        assert result == []

    def test_discovers_skill_dirs_without_manifest_entries(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "_manifest.jsonl").write_text("", encoding="utf-8")
        _make_skill_dir(skills_dir, "my-skill")

        result = read_skill_manifest(tmp_path)

        assert len(result) == 1
        assert result[0].name == "my-skill"
        assert result[0].trigger == "—"
        assert result[0].summary == "—"
        assert result[0].has_skill_md is True

    def test_manifest_entries_populate_trigger_and_summary(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _make_skill_dir(skills_dir, "tdd")
        _write_manifest(
            skills_dir,
            [
                {
                    "name": "tdd",
                    "trigger": "when writing tests",
                    "summary": "red-green-refactor loop",
                },
            ],
        )

        result = read_skill_manifest(tmp_path)

        assert len(result) == 1
        assert result[0].trigger == "when writing tests"
        assert result[0].summary == "red-green-refactor loop"

    def test_ignores_underscore_prefixed_names(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "_index.md").write_text("# index\n", encoding="utf-8")
        # Internal dirs should also be ignored.
        internal = skills_dir / "_internal"
        internal.mkdir()
        (internal / "SKILL.md").write_text("hidden\n", encoding="utf-8")
        dot_internal = skills_dir / ".backups"
        dot_internal.mkdir()
        (dot_internal / "SKILL.md").write_text("hidden\n", encoding="utf-8")
        _make_skill_dir(skills_dir, "visible-skill")

        result = read_skill_manifest(tmp_path)

        names = [e.name for e in result]
        assert "visible-skill" in names
        assert "_internal" not in names
        assert ".backups" not in names

    def test_has_skill_md_false_when_file_missing(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _make_skill_dir(skills_dir, "no-file", with_skill_md=False)

        result = read_skill_manifest(tmp_path)

        assert len(result) == 1
        assert result[0].has_skill_md is False

    def test_corrupt_manifest_line_is_skipped(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _make_skill_dir(skills_dir, "good-skill")
        _make_skill_dir(skills_dir, "bad-skill")
        (skills_dir / "_manifest.jsonl").write_text(
            '{"name": "good-skill", "trigger": "ok"}\nnot json at all\n',
            encoding="utf-8",
        )

        result = read_skill_manifest(tmp_path)

        names = [e.name for e in result]
        assert "good-skill" in names
        # A manifest with at least one valid line is authoritative, so
        # unrelated dirs do not leak into the agent skill catalog.
        assert "bad-skill" not in names
        good = next(e for e in result if e.name == "good-skill")
        assert good.trigger == "ok"

    def test_manifest_is_authoritative_when_present(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _make_skill_dir(skills_dir, "allowed")
        _make_skill_dir(skills_dir, "extra")
        _write_manifest(
            skills_dir,
            [{"name": "allowed", "trigger": "ok", "summary": "listed"}],
        )

        result = read_skill_manifest(tmp_path)

        assert [entry.name for entry in result] == ["allowed"]

    def test_legacy_manifest_falls_back_to_template_manifest(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "workspace"
        skills_dir = workspace / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _make_skill_dir(skills_dir, "skillforge")
        _make_skill_dir(skills_dir, "paw-bootstrap")
        _write_manifest(
            skills_dir,
            [
                {
                    "name": "skillforge",
                    "triggers": ["create skill"],
                    "tools": ["bash"],
                    "category": "meta",
                },
            ],
        )

        template = tmp_path / "template"
        template_skills_dir = template / ".agent" / "skills"
        template_skills_dir.mkdir(parents=True)
        _write_manifest(
            template_skills_dir,
            [
                {
                    "name": "paw-bootstrap",
                    "trigger": "first-run workspace setup",
                    "summary": "Guide initial Paw persona setup.",
                },
            ],
        )
        monkeypatch.setattr(settings, "workspace_template_dir", str(template))

        result = read_skill_manifest(workspace)

        assert [entry.name for entry in result] == ["paw-bootstrap"]
        assert result[0].trigger == "first-run workspace setup"
        assert result[0].summary == "Guide initial Paw persona setup."

    def test_results_sorted_by_name(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        for name in ("zebra", "alpha", "mango"):
            _make_skill_dir(skills_dir, name)

        result = read_skill_manifest(tmp_path)

        assert [e.name for e in result] == ["alpha", "mango", "zebra"]

    def test_returns_empty_on_missing_manifest_file(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _make_skill_dir(skills_dir, "some-skill")
        # No _manifest.jsonl — should still discover via dir scan

        result = read_skill_manifest(tmp_path)

        assert len(result) == 1
        assert result[0].name == "some-skill"
        assert result[0].trigger == "—"
