"""Tests for the skill discovery + invocation agent tools (#315)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.tools.skill_invocation import (
    make_invoke_skill_tool,
    make_list_skills_tool,
    make_read_skill_tool,
)

pytestmark = pytest.mark.anyio


def _make_skill(workspace: Path, name: str, body: str = "# Demo\n\nUse this skill.\n") -> Path:
    skills_dir = workspace / "skills" / name
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skills_dir / "SKILL.md"
    skill_md.write_text(body, encoding="utf-8")
    return skill_md


def _write_manifest(workspace: Path, entries: list[dict]) -> None:
    (workspace / "skills").mkdir(exist_ok=True)
    (workspace / "skills" / "_manifest.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries),
        encoding="utf-8",
    )


async def test_list_skills_empty_workspace_reports_none(tmp_path: Path) -> None:
    tool = make_list_skills_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1")
    assert "No skills" in result


async def test_list_skills_renders_each_entry(tmp_path: Path) -> None:
    _make_skill(tmp_path, "tdd")
    _write_manifest(
        tmp_path,
        [{"name": "tdd", "trigger": "red-green-refactor", "summary": "TDD loop"}],
    )

    tool = make_list_skills_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1")
    assert "tdd" in result
    assert "red-green-refactor" in result
    assert "TDD loop" in result


async def test_read_skill_returns_bounded_body(tmp_path: Path) -> None:
    _make_skill(tmp_path, "demo", body="# Demo\n\nLine 1\nLine 2\n")
    tool = make_read_skill_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1", name="demo")
    assert "# Skill: demo" in result
    assert "Line 1" in result
    assert "Line 2" in result


async def test_read_skill_unknown_name_returns_not_found(tmp_path: Path) -> None:
    tool = make_read_skill_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1", name="nope")
    assert "NOT_FOUND" in result or "no SKILL.md" in result


async def test_read_skill_rejects_path_traversal(tmp_path: Path) -> None:
    tool = make_read_skill_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1", name="../../../etc")
    assert "INVALID_PATH" in result or "not a simple skill identifier" in result


async def test_read_skill_truncates_huge_body(tmp_path: Path) -> None:
    # 2_000 lines comfortably exceeds the 800 cap.
    huge = "\n".join(f"line {i}" for i in range(2_000))
    _make_skill(tmp_path, "huge", body=huge)
    tool = make_read_skill_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1", name="huge")
    assert "[truncated]" in result


async def test_invoke_skill_wraps_body_with_markers(tmp_path: Path) -> None:
    _make_skill(tmp_path, "demo", body="# Demo skill\n\nFollow steps.\n")
    tool = make_invoke_skill_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1", name="demo", reason="user asked")
    assert "Invoking skill 'demo'" in result
    assert "BEGIN SKILL INSTRUCTIONS" in result
    assert "END SKILL INSTRUCTIONS" in result
    assert "Follow steps." in result
    assert "user asked" in result


async def test_invoke_skill_requires_name(tmp_path: Path) -> None:
    tool = make_invoke_skill_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1")
    assert "required" in result.lower() or "INVALID_PATH" in result


async def test_invoke_skill_unknown_returns_not_found(tmp_path: Path) -> None:
    tool = make_invoke_skill_tool(workspace_root=tmp_path)
    result = await tool.execute(tool_call_id="t1", name="missing")
    assert "NOT_FOUND" in result or "no SKILL.md" in result
