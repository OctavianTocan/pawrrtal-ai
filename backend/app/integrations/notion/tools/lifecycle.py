"""Lifecycle Notion tools: delete (archive), move, publish."""

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


def make_notion_delete_tool(ctx: ToolContext) -> AgentTool:
    """Archive a Notion page (Notion has no hard delete).

    Maps to ``PATCH /v1/pages/{id} {"archived": true}`` so the page is
    moved to Trash and can be restored from the Notion UI — matching
    openclaw-notion's contract.
    """
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        if not page_id:
            return encode_error("page_id is required")

        body = json.dumps({"archived": True})

        async def _do() -> Any:
            return await call_ntn_json(
                ["api", f"v1/pages/{page_id}", "-X", "PATCH", "-d", body],
                token=token,
            )

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_delete",
                operation="delete",
                request={"page_id": page_id},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_delete",
        description=(
            "Archive (soft-delete) a Notion page. The page moves to Trash "
            "and can be restored via the Notion UI."
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID (UUID)."},
            },
            "required": ["page_id"],
        },
        execute=execute,
    )


def make_notion_move_tool(ctx: ToolContext) -> AgentTool:
    """Re-parent a Notion page under a new parent page."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        new_parent_id = str(params.get("new_parent_page_id") or "")
        if not page_id or not new_parent_id:
            return encode_error("page_id and new_parent_page_id are required")

        body = json.dumps({"parent": {"page_id": new_parent_id}})

        async def _do() -> Any:
            return await call_ntn_json(
                ["api", f"v1/pages/{page_id}", "-X", "PATCH", "-d", body],
                token=token,
            )

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_move",
                operation="write",
                request={"page_id": page_id, "new_parent_page_id": new_parent_id},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_move",
        description="Re-parent a Notion page under a different parent page.",
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page to move (UUID)."},
                "new_parent_page_id": {
                    "type": "string",
                    "description": "Destination parent page (UUID).",
                },
            },
            "required": ["page_id", "new_parent_page_id"],
        },
        execute=execute,
    )


def make_notion_publish_tool(ctx: ToolContext) -> AgentTool:
    """Toggle Notion page-level public sharing on or off.

    Notion exposes share state via the ``public_url`` property on a
    page; PATCHing ``{"public_url": {"public": true}}`` flips it.
    Useful for "make this page public" agent prompts.
    """
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        public = bool(params.get("public", True))
        if not page_id:
            return encode_error("page_id is required")

        body = json.dumps({"public_url": {"public": public}})

        async def _do() -> Any:
            return await call_ntn_json(
                ["api", f"v1/pages/{page_id}", "-X", "PATCH", "-d", body],
                token=token,
            )

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_publish",
                operation="write",
                request={"page_id": page_id, "public": public},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_publish",
        description=(
            "Toggle a Notion page's public sharing state. Pass `public: true` "
            "to make the page accessible via a public URL; `false` to revoke."
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID (UUID)."},
                "public": {
                    "type": "boolean",
                    "description": "Target sharing state.",
                    "default": True,
                },
            },
            "required": ["page_id"],
        },
        execute=execute,
    )
