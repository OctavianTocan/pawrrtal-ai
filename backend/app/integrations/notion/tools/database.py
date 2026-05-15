"""Notion database query tool."""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.plugins.types import ToolContext
from app.integrations.notion.audit import with_audit
from app.integrations.notion.ntn_client import NtnError, call_ntn_json
from app.integrations.notion.tools._helpers import (
    build_tool,
    encode_error,
    encode_result,
    missing_token_error,
    require_token,
)

DEFAULT_QUERY_PAGE_SIZE = 25
MAX_QUERY_PAGE_SIZE = 100


def make_notion_query_tool(ctx: ToolContext) -> AgentTool:
    """Query a Notion database with optional filter / sort objects."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        database_id = str(params.get("database_id") or "")
        if not database_id:
            return encode_error("database_id is required")

        body_dict: dict[str, Any] = {
            "page_size": min(
                int(params.get("page_size") or DEFAULT_QUERY_PAGE_SIZE),
                MAX_QUERY_PAGE_SIZE,
            ),
        }
        filter_obj = params.get("filter")
        if isinstance(filter_obj, dict) and filter_obj:
            body_dict["filter"] = filter_obj
        sorts_obj = params.get("sorts")
        if isinstance(sorts_obj, list) and sorts_obj:
            body_dict["sorts"] = sorts_obj
        body = json.dumps(body_dict)

        async def _do() -> Any:
            args = [
                "api",
                f"v1/databases/{database_id}/query",
                "-X",
                "POST",
                "-d",
                body,
            ]
            return await call_ntn_json(args, token=token)

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_query",
                operation="read",
                request={"database_id": database_id, **body_dict},
                database_id=database_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_query",
        description=(
            "Query a Notion database. Accepts an optional Notion-shaped "
            "`filter` object and `sorts` array; both default to none."
        ),
        parameters={
            "type": "object",
            "properties": {
                "database_id": {
                    "type": "string",
                    "description": "Database ID (UUID).",
                },
                "filter": {
                    "type": "object",
                    "description": "Notion filter object (optional).",
                },
                "sorts": {
                    "type": "array",
                    "description": "Notion sort array (optional).",
                    "items": {"type": "object"},
                },
                "page_size": {
                    "type": "integer",
                    "description": (
                        f"Max rows (1-{MAX_QUERY_PAGE_SIZE}). Default {DEFAULT_QUERY_PAGE_SIZE}."
                    ),
                    "minimum": 1,
                    "maximum": MAX_QUERY_PAGE_SIZE,
                    "default": DEFAULT_QUERY_PAGE_SIZE,
                },
            },
            "required": ["database_id"],
        },
        execute=execute,
    )
