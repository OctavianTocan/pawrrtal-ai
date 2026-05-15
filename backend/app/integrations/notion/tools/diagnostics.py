"""Diagnostic Notion tools: help, doctor, logs read.

These three don't touch Notion's API beyond a connectivity probe in
``notion_doctor``; their job is to make the integration self-describing
for the agent so it can answer "is Notion configured?" / "what tools
do I have?" / "show me the last few operations" without falling back
to free-form text.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.agent_loop.types import AgentTool
from app.core.plugins.types import ToolContext
from app.db import async_session_maker
from app.integrations.notion.audit import with_audit
from app.integrations.notion.ntn_client import NtnError, call_ntn_json
from app.integrations.notion.tools._helpers import (
    build_tool,
    encode_error,
    encode_result,
    missing_token_error,
    require_token,
)
from app.models import NotionOperationLog

DEFAULT_LOGS_LIMIT = 20
MAX_LOGS_LIMIT = 100


def make_notion_help_tool(ctx: ToolContext) -> AgentTool:
    """Return a static catalogue of the plugin's eighteen tools."""

    async def execute(_tool_call_id: str, _params: dict[str, Any]) -> str:
        # Help is intentionally static — the catalogue can't change at
        # runtime without a code deploy, so audit-logging this would be
        # noise.  Skip ``with_audit`` on this one tool.
        catalogue = {
            "tools": [
                {"name": "notion_search", "summary": "Search workspace by query."},
                {"name": "notion_read", "summary": "Read a page as raw block JSON."},
                {"name": "notion_read_markdown", "summary": "Read a page as Markdown."},
                {"name": "notion_append", "summary": "Append blocks to a page."},
                {"name": "notion_create", "summary": "Create a new page from Markdown."},
                {"name": "notion_update_markdown", "summary": "Replace a page body."},
                {"name": "notion_update_page", "summary": "PATCH page properties."},
                {"name": "notion_comment_create", "summary": "Post a comment to a page."},
                {"name": "notion_comment_list", "summary": "List comments on a page."},
                {"name": "notion_query", "summary": "Query a Notion database."},
                {"name": "notion_delete", "summary": "Archive (soft-delete) a page."},
                {"name": "notion_move", "summary": "Re-parent a page."},
                {"name": "notion_publish", "summary": "Toggle public sharing on a page."},
                {"name": "notion_file_tree", "summary": "Recursively map child pages."},
                {"name": "notion_sync", "summary": "Push/pull a local markdown file."},
                {"name": "notion_help", "summary": "This tool — list all Notion tools."},
                {"name": "notion_doctor", "summary": "Health-check the connection."},
                {"name": "notion_logs_read", "summary": "Show recent Notion operations."},
            ],
        }
        return encode_result(catalogue)

    return build_tool(
        name="notion_help",
        description="List every Notion tool available in this plugin.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
    )


def make_notion_doctor_tool(ctx: ToolContext) -> AgentTool:
    """Connectivity probe — calls ``v1/users/me`` to confirm auth works."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, _params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()

        async def _do() -> Any:
            return await call_ntn_json(["api", "v1/users/me"], token=token)

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_doctor",
                operation="diagnostic",
                request=None,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(
            {
                "ok": True,
                "bot": {
                    "id": result.get("id") if isinstance(result, dict) else None,
                    "name": result.get("name") if isinstance(result, dict) else None,
                },
            }
        )

    return build_tool(
        name="notion_doctor",
        description=(
            "Health-check the Notion connection. Calls /v1/users/me and "
            "returns the bot's id/name on success, or an error otherwise."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
    )


def make_notion_logs_read_tool(ctx: ToolContext) -> AgentTool:
    """Read the last N audit rows for this workspace."""

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        limit = min(int(params.get("limit") or DEFAULT_LOGS_LIMIT), MAX_LOGS_LIMIT)
        tool_filter = str(params.get("tool_name") or "").strip()

        async with async_session_maker() as session:
            query = (
                select(NotionOperationLog)
                .where(NotionOperationLog.workspace_id == ctx.workspace_id)
                .order_by(NotionOperationLog.created_at.desc())
                .limit(limit)
            )
            if tool_filter:
                query = query.where(NotionOperationLog.tool_name == tool_filter)
            rows = (await session.execute(query)).scalars().all()

        return encode_result(
            {
                "logs": [
                    {
                        "id": str(row.id),
                        "tool_name": row.tool_name,
                        "operation": row.operation,
                        "status": row.status,
                        "duration_ms": row.duration_ms,
                        "page_id": row.page_id,
                        "database_id": row.database_id,
                        "error": row.error,
                        "created_at": row.created_at.isoformat(),
                    }
                    for row in rows
                ],
            }
        )

    return build_tool(
        name="notion_logs_read",
        description=(
            "Return recent Notion operation logs for this workspace, "
            "newest first. Filter by tool name with `tool_name`."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": f"Max rows (1-{MAX_LOGS_LIMIT}).",
                    "minimum": 1,
                    "maximum": MAX_LOGS_LIMIT,
                    "default": DEFAULT_LOGS_LIMIT,
                },
                "tool_name": {
                    "type": "string",
                    "description": "Filter to one tool name (optional).",
                },
            },
        },
        execute=execute,
    )
