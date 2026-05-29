"""Tests for the report_issue agent tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.tools.report_issue import make_report_issue_tool  # noqa: E402

pytestmark = pytest.mark.anyio

FAKE_TOKEN = "ghp_test123"
FAKE_REPO = "octaviantocan/pawrrtal-ai"


def _mock_github_response(
    status_code: int = 201,
    issue_number: int = 42,
    html_url: str = "https://github.com/octaviantocan/pawrrtal-ai/issues/42",
) -> httpx.Response:
    """Build a fake httpx.Response for GitHub issue creation."""
    body = json.dumps(
        {
            "number": issue_number,
            "html_url": html_url,
            "id": 123456,
        }
    )
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", "https://api.github.com/repos/test/issues"),
        content=body.encode(),
        headers={"content-type": "application/json"},
    )


def _patch_github(
    response: httpx.Response | None = None,
) -> Any:
    """Return a context manager that patches httpx.AsyncClient.post."""
    resp = response or _mock_github_response()
    mock_post = AsyncMock(return_value=resp)
    return patch.object(httpx.AsyncClient, "post", mock_post)


def _patch_token(token: str | None = FAKE_TOKEN) -> Any:
    """Patch resolve_api_key to return the given token."""
    return patch(
        "app.tools.report_issue.resolve_api_key",
        return_value=token,
    )


def _patch_repo(repo: str = FAKE_REPO) -> Any:
    """Patch settings.github_issues_repo."""
    return patch(
        "app.tools.report_issue.settings",
        github_issues_repo=repo,
    )


async def test_report_issue_creates_github_issue(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    with _patch_token(), _patch_repo(), _patch_github() as mock_post:
        result = await tool.execute(
            "call-1",
            title="Fix login redirect loop",
            body="After OAuth callback the router enters an infinite redirect.",
            type="bug",
            priority="high",
        )

    parsed = json.loads(result)
    assert parsed["created"] is True
    assert parsed["number"] == 42
    assert "github.com" in parsed["url"]
    mock_post.assert_called_once()

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["title"] == "Fix login redirect loop"
    assert "agent-reported" in payload["labels"]
    assert "bug" in payload["labels"]
    assert "priority:high" in payload["labels"]


async def test_report_issue_includes_steps_to_reproduce(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    with _patch_token(), _patch_repo(), _patch_github() as mock_post:
        await tool.execute(
            "call-1",
            title="Button unresponsive",
            body="The submit button does nothing on click.",
            type="bug",
            priority="normal",
            steps_to_reproduce="1. Go to /settings\n2. Click Save",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert "Steps to Reproduce" in payload["body"]
    assert "1. Go to /settings" in payload["body"]


async def test_report_issue_rejects_empty_title(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    result = await tool.execute(
        "call-1",
        title="",
        body="Some body",
        type="bug",
        priority="low",
    )
    assert "title" in result
    assert "required" in result


async def test_report_issue_rejects_empty_body(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    result = await tool.execute(
        "call-1",
        title="Valid title",
        body="  ",
        type="bug",
        priority="low",
    )
    assert "body" in result
    assert "required" in result


async def test_report_issue_rejects_invalid_type(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    result = await tool.execute(
        "call-1",
        title="Title",
        body="Body",
        type="invalid",
        priority="low",
    )
    assert "type" in result
    assert "must be one of" in result


async def test_report_issue_rejects_invalid_priority(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    result = await tool.execute(
        "call-1",
        title="Title",
        body="Body",
        type="bug",
        priority="urgent",
    )
    assert "priority" in result
    assert "must be one of" in result


async def test_report_issue_handles_missing_token(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    with _patch_token(None), _patch_repo():
        result = await tool.execute(
            "call-1",
            title="Title",
            body="Body",
            type="bug",
            priority="low",
        )
    assert "GITHUB_TOKEN" in result
    assert "not configured" in result


async def test_report_issue_handles_api_error(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    error_response = _mock_github_response(status_code=422)
    with _patch_token(), _patch_repo(), _patch_github(error_response):
        result = await tool.execute(
            "call-1",
            title="Title",
            body="Body",
            type="bug",
            priority="low",
        )
    parsed = json.loads(result)
    assert parsed["created"] is False
    assert "422" in parsed["error"]


async def test_report_issue_maps_type_to_labels(tmp_path: Path) -> None:
    tool = make_report_issue_tool(workspace_root=tmp_path)
    with _patch_token(), _patch_repo(), _patch_github() as mock_post:
        await tool.execute(
            "call-1",
            title="Add dark mode",
            body="Users want dark mode support.",
            type="feature",
            priority="normal",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert "enhancement" in payload["labels"]
    assert "priority:normal" in payload["labels"]
