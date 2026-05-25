"""build_agent_tools wiring tests for all LCM tools.

These tests were deferred from PRs 7-9 because they require
build_agent_tools to accept conversation_id and model_id (this PR).

Covers:
- lcm_grep is present when lcm_enabled=True and conversation_id is set
- lcm_grep is absent when lcm_enabled=False
- lcm_grep is absent when conversation_id is None
- lcm_describe and lcm_list_summaries are present/absent under the same gates
- lcm_expand_query is present only when user_id is also provided
- lcm_expand_query is absent when user_id is None
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest


def test_lcm_grep_tool_present_when_lcm_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", True)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    tools = build_agent_tools(workspace_root=tmp_path, conversation_id=uuid.uuid4())
    assert "lcm_grep" in [t.name for t in tools]


def test_lcm_grep_tool_absent_when_lcm_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", False)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    tools = build_agent_tools(workspace_root=tmp_path, conversation_id=uuid.uuid4())
    assert "lcm_grep" not in [t.name for t in tools]


def test_lcm_grep_tool_absent_when_no_conversation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", True)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    tools = build_agent_tools(workspace_root=tmp_path, conversation_id=None)
    assert "lcm_grep" not in [t.name for t in tools]


def test_describe_tools_present_when_lcm_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", True)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    tools = build_agent_tools(workspace_root=tmp_path, conversation_id=uuid.uuid4())
    names = [t.name for t in tools]
    assert "lcm_list_summaries" in names
    assert "lcm_describe" in names


def test_describe_tools_absent_when_lcm_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", False)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    tools = build_agent_tools(workspace_root=tmp_path, conversation_id=uuid.uuid4())
    names = [t.name for t in tools]
    assert "lcm_list_summaries" not in names
    assert "lcm_describe" not in names


def test_expand_query_tool_present_when_user_id_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", True)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    tools = build_agent_tools(
        workspace_root=tmp_path,
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    assert "lcm_expand_query" in [t.name for t in tools]


def test_expand_query_tool_absent_without_user_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", True)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    # user_id=None → expand_query should NOT be present (it needs user_id for
    # the LLM sub-call).
    tools = build_agent_tools(
        workspace_root=tmp_path,
        conversation_id=uuid.uuid4(),
        user_id=None,
    )
    assert "lcm_expand_query" not in [t.name for t in tools]


def test_expand_query_tool_absent_when_lcm_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config as _cfg
    from app.core.agent_loop.tools import build_agent_tools

    monkeypatch.setattr(_cfg.settings, "lcm_enabled", False)
    monkeypatch.setattr(_cfg.settings, "exa_api_key", None)

    tools = build_agent_tools(
        workspace_root=tmp_path,
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    assert "lcm_expand_query" not in [t.name for t in tools]
