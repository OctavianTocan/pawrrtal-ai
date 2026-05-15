"""Notion comment tools: create and list comments on a page."""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.plugins.types import ToolContext
from app.integrations.notion.audit import with_audit
from app.integrations.notion.ntn_client import NtnError, call_ntn_json, format_query_params
from app.integrations.notion.tools._helpers import (
    build_tool,
    encode_error,
    encode_result,
    missing_token_error,
    require_token,
)

DEFAULT_COMMENT_PAGE_SIZE = 25
MAX_COMMENT_PAGE_SIZE = 100


def make_notion_comment_create_tool(ctx: ToolContext) -> AgentTool:
    """Post a comment to a Notion page."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        text = str(params.get("text") or "")
        if not page_id or not text:
            return encode_error("page_id and text are required")

        body = json.dumps(
            {
                "parent": {"page_id": page_id},
                "rich_text": [{"type": "text", "text": {"content": text}}],
            }
        )

        async def _do() -> Any:
            return await call_ntn_json(
                ["api", "v1/comments", "-X", "POST", "-d", body], token=token
            )

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_comment_create",
                operation="write",
                request={"page_id": page_id, "text_chars": len(text)},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_comment_create",
        description="Add a comment to a Notion page.",
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID (UUID)."},
                "text": {"type": "string", "description": "Comment text."},
            },
            "required": ["page_id", "text"],
        },
        execute=execute,
    )


def make_notion_comment_list_tool(ctx: ToolContext) -> AgentTool:
    """List comments on a Notion page."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        page_size = min(
            int(params.get("page_size") or DEFAULT_COMMENT_PAGE_SIZE),
            MAX_COMMENT_PAGE_SIZE,
        )
        if not page_id:
            return encode_error("page_id is required")

        async def _do() -> Any:
            args = [
                "api",
                "v1/comments",
                *format_query_params({"block_id": page_id, "page_size": str(page_size)}),
            ]
            return await call_ntn_json(args, token=token)

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_comment_list",
                operation="read",
                request={"page_id": page_id, "page_size": page_size},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_comment_list",
        description="List comments on a Notion page, newest first.",
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID (UUID)."},
                "page_size": {
                    "type": "integer",
                    "description": (
                        f"Max comments to return (1-{MAX_COMMENT_PAGE_SIZE}). "
                        f"Default {DEFAULT_COMMENT_PAGE_SIZE}."
                    ),
                    "minimum": 1,
                    "maximum": MAX_COMMENT_PAGE_SIZE,
                    "default": DEFAULT_COMMENT_PAGE_SIZE,
                },
            },
            "required": ["page_id"],
        },
        execute=execute,
    )
