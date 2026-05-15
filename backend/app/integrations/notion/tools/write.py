"""Mutating Notion tools: append, create, update markdown, update page title.

``notion_create`` and ``notion_update_markdown`` use the markdown-native
``ntn pages`` commands; ``notion_append`` and ``notion_update_page``
use the generic ``ntn api`` route so we can target individual blocks
and arbitrary page properties.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.plugins.types import ToolContext
from app.integrations.notion.audit import with_audit
from app.integrations.notion.ntn_client import NtnError, call_ntn_json, call_ntn_text
from app.integrations.notion.tools._helpers import (
    build_tool,
    encode_error,
    encode_result,
    missing_token_error,
    require_token,
)


def make_notion_append_tool(ctx: ToolContext) -> AgentTool:
    """Append blocks to a page via ``v1/blocks/<id>/children`` PATCH."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        children = params.get("children")
        if not page_id:
            return encode_error("page_id is required")
        if not isinstance(children, list) or not children:
            return encode_error("children must be a non-empty list of block objects")

        body = json.dumps({"children": children})

        async def _do() -> Any:
            args = [
                "api",
                f"v1/blocks/{page_id}/children",
                "-X",
                "PATCH",
                "-d",
                body,
            ]
            return await call_ntn_json(args, token=token)

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_append",
                operation="write",
                request={"page_id": page_id, "block_count": len(children)},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_append",
        description=(
            "Append one or more Notion block objects to a page. `children` "
            "is the Notion-shaped block array (e.g. "
            '[{"object":"block","type":"paragraph",...}]).'
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID (UUID)."},
                "children": {
                    "type": "array",
                    "description": "Notion block objects to append.",
                    "items": {"type": "object"},
                },
            },
            "required": ["page_id", "children"],
        },
        execute=execute,
    )


def make_notion_create_tool(ctx: ToolContext) -> AgentTool:
    """Create a new page under a parent via ``ntn pages create``."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        parent_id = str(params.get("parent_page_id") or "")
        title = str(params.get("title") or "")
        markdown = str(params.get("markdown") or "")
        if not parent_id or not title:
            return encode_error("parent_page_id and title are required")

        async def _do() -> Any:
            args = [
                "pages",
                "create",
                "--parent",
                f"page:{parent_id}",
                "--title",
                title,
                "--content",
                markdown,
            ]
            # ``ntn pages create`` returns text confirming the new page;
            # use call_ntn_text and surface that directly.
            text = await call_ntn_text(args, token=token)
            return {"output": text}

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_create",
                operation="write",
                request={
                    "parent_page_id": parent_id,
                    "title": title,
                    "markdown_chars": len(markdown),
                },
                page_id=parent_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_create",
        description=(
            "Create a new Notion page under `parent_page_id` with a "
            "Markdown body. Returns the CLI confirmation including the "
            "new page's URL."
        ),
        parameters={
            "type": "object",
            "properties": {
                "parent_page_id": {
                    "type": "string",
                    "description": "Parent page UUID; the new page lands under it.",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the new page.",
                },
                "markdown": {
                    "type": "string",
                    "description": "Markdown body. Empty string for an empty page.",
                    "default": "",
                },
            },
            "required": ["parent_page_id", "title"],
        },
        execute=execute,
    )


def make_notion_update_markdown_tool(ctx: ToolContext) -> AgentTool:
    """Replace a page's body with new Markdown via ``ntn pages update``."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        markdown = str(params.get("markdown") or "")
        if not page_id:
            return encode_error("page_id is required")

        async def _do() -> Any:
            args = ["pages", "update", page_id, "--content", markdown]
            text = await call_ntn_text(args, token=token)
            return {"output": text}

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_update_markdown",
                operation="write",
                request={"page_id": page_id, "markdown_chars": len(markdown)},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_update_markdown",
        description=(
            "Replace a Notion page's body with the provided Markdown. "
            "Pair with notion_read_markdown for a full read-edit-write loop."
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID (UUID)."},
                "markdown": {
                    "type": "string",
                    "description": "New Markdown body for the page.",
                },
            },
            "required": ["page_id", "markdown"],
        },
        execute=execute,
    )


def make_notion_update_page_tool(ctx: ToolContext) -> AgentTool:
    """Patch page-level properties (title, icon, cover, archive flag)."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        properties = params.get("properties") or {}
        if not page_id or not isinstance(properties, dict) or not properties:
            return encode_error("page_id and a non-empty properties object are required")

        body = json.dumps({"properties": properties})

        async def _do() -> Any:
            args = ["api", f"v1/pages/{page_id}", "-X", "PATCH", "-d", body]
            return await call_ntn_json(args, token=token)

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_update_page",
                operation="write",
                request={"page_id": page_id, "property_keys": list(properties)},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_update_page",
        description=(
            "Patch a Notion page's properties (title, icon, cover, etc.). "
            "Pass a Notion-shaped `properties` object; only the keys you "
            "include are touched. Use notion_update_markdown for body edits."
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID (UUID)."},
                "properties": {
                    "type": "object",
                    "description": "Notion `properties` object to PATCH.",
                },
            },
            "required": ["page_id", "properties"],
        },
        execute=execute,
    )
