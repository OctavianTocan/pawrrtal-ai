"""``report_issue`` AgentTool — create GitHub issues directly.

Gives the agent a way to report bugs, improvements, and feature
requests it encounters during a conversation. The tool POSTs to the
GitHub REST API and returns the created issue URL. Capability-gated
on ``GITHUB_TOKEN`` being configured (workspace or global).

Fields are intentionally minimal — title, body, type, priority, and
an optional steps-to-reproduce block — so the agent can file quickly
without over-thinking the schema. Labels are auto-applied from the
type and priority values.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from app.agents.types import AgentTool
from app.infrastructure.config import settings
from app.infrastructure.keys import resolve_api_key
from app.tools.display import make_tool_display, truncate_text
from app.tools.errors import ToolError, ToolErrorCode

log = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_TIMEOUT_SECONDS = 15.0
HTTP_CREATED = 201

MAX_TITLE_LEN = 120
MAX_BODY_LEN = 4000
MAX_STEPS_LEN = 2000

VALID_TYPES = frozenset({"bug", "feature", "improvement", "chore"})
VALID_PRIORITIES = frozenset({"low", "normal", "high", "critical"})

_TYPE_TO_LABEL: dict[str, str] = {
    "bug": "bug",
    "feature": "enhancement",
    "improvement": "enhancement",
    "chore": "chore",
}

AGENT_REPORTED_LABEL = "agent-reported"


def _validate_required_string(
    value: Any,
    field_name: str,
    max_len: int,
) -> str:
    """Return trimmed string or raise ToolError."""
    text = str(value or "").strip()
    if not text:
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"'{field_name}' is required and must be non-empty.",
        )
    if len(text) > max_len:
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"'{field_name}' exceeds {max_len} characters ({len(text)}).",
        )
    return text


def _validate_enum(value: Any, field_name: str, allowed: frozenset[str]) -> str:
    """Return validated enum string or raise ToolError."""
    text = str(value or "").strip().lower()
    if text not in allowed:
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"'{field_name}' must be one of {sorted(allowed)}, got '{text}'.",
        )
    return text


def _validate_optional_steps(value: Any) -> str | None:
    """Return trimmed steps string, None if empty, or raise ToolError."""
    if not value or not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) > MAX_STEPS_LEN:
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"'steps_to_reproduce' exceeds {MAX_STEPS_LEN} characters ({len(text)}).",
        )
    return text


def _build_issue_body(
    body: str,
    issue_type: str,
    priority: str,
    steps: str | None,
) -> str:
    """Format the GitHub issue body with metadata and optional sections."""
    sections = [body]

    if steps:
        sections.append(f"## Steps to Reproduce\n\n{steps}")

    metadata = f"**Type:** {issue_type} | **Priority:** {priority}"
    sections.append(f"---\n\n{metadata}")
    return "\n\n".join(sections)


def _build_labels(issue_type: str, priority: str) -> list[str]:
    """Derive GitHub labels from type and priority."""
    labels = [AGENT_REPORTED_LABEL]
    type_label = _TYPE_TO_LABEL.get(issue_type)
    if type_label:
        labels.append(type_label)
    labels.append(f"priority:{priority}")
    return labels


async def _create_github_issue(
    token: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
) -> dict[str, Any]:
    """POST to GitHub REST API to create an issue.

    Returns the parsed JSON response on success.
    Raises httpx.HTTPStatusError on non-201 responses.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": body, "labels": labels}

    async with httpx.AsyncClient(timeout=GITHUB_API_TIMEOUT_SECONDS) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


def make_report_issue_tool(*, workspace_root: Path) -> AgentTool:
    """Return the ``report_issue`` :class:`AgentTool`.

    The tool resolves ``GITHUB_TOKEN`` at call time via
    :func:`resolve_api_key` so it picks up workspace-level overrides.
    The target repo comes from ``settings.github_issues_repo``.
    """

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        try:
            title = _validate_required_string(kwargs.get("title"), "title", MAX_TITLE_LEN)
            body = _validate_required_string(kwargs.get("body"), "body", MAX_BODY_LEN)
            issue_type = _validate_enum(kwargs.get("type"), "type", VALID_TYPES)
            priority = _validate_enum(kwargs.get("priority"), "priority", VALID_PRIORITIES)
            steps = _validate_optional_steps(kwargs.get("steps_to_reproduce"))
        except ToolError as err:
            return err.render()

        token = resolve_api_key(workspace_root, "GITHUB_TOKEN")
        repo = settings.github_issues_repo
        if not token or not repo:
            missing = "GITHUB_TOKEN" if not token else "GITHUB_ISSUES_REPO"
            return ToolError(
                ToolErrorCode.PERMISSION_DENIED,
                f"{missing} is not configured. Set it in the workspace "
                "environment or global settings to enable issue reporting.",
            ).render()

        formatted_body = _build_issue_body(body, issue_type, priority, steps)
        labels = _build_labels(issue_type, priority)

        try:
            result = await _create_github_issue(token, repo, title, formatted_body, labels)
        except httpx.HTTPStatusError as exc:
            log.warning(
                "GitHub issue creation failed: status=%d body=%s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return json.dumps(
                {
                    "created": False,
                    "error": f"GitHub API returned {exc.response.status_code}",
                }
            )
        except httpx.TimeoutException:
            log.warning("GitHub issue creation timed out for title=%r", title)
            return json.dumps({"created": False, "error": "Request timed out"})

        issue_url = result.get("html_url", "")
        issue_number = result.get("number", "?")
        log.info("Created GitHub issue #%s: %s", issue_number, issue_url)
        return json.dumps(
            {
                "created": True,
                "number": issue_number,
                "url": issue_url,
            }
        )

    return AgentTool(
        name="report_issue",
        description=(
            "Report a bug, improvement, or feature request by creating a "
            "GitHub issue. Use this when you notice something broken, "
            "suboptimal, or missing during the conversation -- even if the "
            "user didn't explicitly ask. Include enough context in 'body' "
            "(file paths, error messages, expected vs actual behavior) that "
            "a developer reading the issue can act on it without "
            "re-discovering the problem."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Short imperative summary for the issue title "
                        "(e.g. 'Fix login redirect loop on Safari'). "
                        f"Max {MAX_TITLE_LEN} characters."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": (
                        "Detailed description of the issue. For bugs: "
                        "what happened, what was expected. For features: "
                        "what to build and why. Include file paths and "
                        f"code references when relevant. Max {MAX_BODY_LEN} characters."
                    ),
                },
                "type": {
                    "type": "string",
                    "enum": sorted(VALID_TYPES),
                    "description": "The kind of issue being reported.",
                },
                "priority": {
                    "type": "string",
                    "enum": sorted(VALID_PRIORITIES),
                    "description": (
                        "How urgent the issue is. Use 'critical' only for "
                        "data loss or security issues."
                    ),
                },
                "steps_to_reproduce": {
                    "type": "string",
                    "description": (
                        "Optional step-by-step reproduction instructions "
                        "for bugs. Omit for features and improvements."
                    ),
                },
            },
            "required": ["title", "body", "type", "priority"],
        },
        execute=execute,
        display=make_tool_display(
            icon="🐛",
            label="Report Issue",
            present=_report_issue_present,
            compact=_report_issue_compact,
        ),
    )


def _report_issue_present(args: dict[str, Any]) -> str:
    title = truncate_text(str(args.get("title") or ""), 60)
    return f"🐛 Reporting: {title}" if title else "🐛 Reporting issue"


def _report_issue_compact(args: dict[str, Any]) -> str:
    title = truncate_text(str(args.get("title") or ""), 40)
    return f"report_issue({title})" if title else "report_issue()"
