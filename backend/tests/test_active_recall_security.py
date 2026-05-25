"""Security tests for the active recall plugin and workspace tools."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.core.agent_loop.types import AgentTool, PermissionCheckResult
from app.core.plugins.types import PreTurnHookContext
from app.core.tools.workspace_files import make_workspace_tools
from app.plugins.active_recall.recall_agent import run_active_recall


class CapturingProvider:
    """Mock provider that captures arguments and allows executing tools."""

    def __init__(self) -> None:
        self.captured_permission_check: Any = None
        self.captured_tools: list[AgentTool] = []

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: str | None = None,
        permission_check: Any = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        self.captured_permission_check = permission_check
        self.captured_tools = tools or []
        # Return a simple done event
        yield {"type": "delta", "content": "NONE"}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with both safe and forbidden files."""
    (tmp_path / "AGENTS.md").write_text("# Agent rules\n", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=secret_val\n", encoding="utf-8")
    (tmp_path / "private.pem").write_text("PEM_DATA\n", encoding="utf-8")
    return tmp_path


@pytest.mark.anyio
async def test_list_dir_filters_out_forbidden_filenames(workspace: Path) -> None:
    """Verify that forbidden filenames are hidden from directory listings."""
    tools = {tool.name: tool for tool in make_workspace_tools(workspace)}
    list_dir_tool = tools["list_dir"]

    out = await list_dir_tool.execute("call-1")
    assert "AGENTS.md" in out
    assert ".env" not in out
    assert "private.pem" not in out


@pytest.mark.anyio
async def test_run_active_recall_enforces_permission_check(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify active recall passes permission_check and blocks .env access."""
    provider = CapturingProvider()
    monkeypatch.setattr(
        "app.plugins.active_recall.recall_agent.resolve_llm",
        lambda *args, **kwargs: provider,
    )
    # Enable active recall and LCM search for the test
    monkeypatch.setattr(
        "app.plugins.active_recall.recall_agent.settings",
        type("Settings", (), {"lcm_enabled": True})(),
    )

    ctx = PreTurnHookContext(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        question="What are my files?",
        workspace_root=workspace,
        draft_updater=None,
    )

    # Execute active recall. It will invoke CapturingProvider.stream.
    await run_active_recall(ctx)

    assert provider.captured_permission_check is not None

    # Verify that permission check allows reading safe files
    result_safe: PermissionCheckResult = await provider.captured_permission_check(
        "read_file", {"path": "AGENTS.md"}
    )
    assert result_safe["allow"] is True

    # Verify that permission check denies reading forbidden files (like .env)
    result_env: PermissionCheckResult = await provider.captured_permission_check(
        "read_file", {"path": ".env"}
    )
    assert result_env["allow"] is False
    assert result_env["violation_type"] == "forbidden_filename"

    # Verify that permission check denies reading files matching dangerous patterns
    result_pem: PermissionCheckResult = await provider.captured_permission_check(
        "read_file", {"path": "private.pem"}
    )
    assert result_pem["allow"] is False
    assert result_pem["violation_type"] == "forbidden_filename"
