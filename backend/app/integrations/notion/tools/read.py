"""Read-side Notion tools: search, read blocks, read markdown, file tree.

All four are non-mutating.  ``notion_read_markdown`` uses the dedicated
``ntn pages get`` command (markdown-native); the rest go through the
generic ``ntn api`` escape hatch.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.agent_loop.types import AgentTool
from app.core.plugins.types import ToolContext
from app.integrations.notion.audit import with_audit
from app.integrations.notion.ntn_client import (
    NtnError,
    call_ntn_json,
    call_ntn_text,
    format_query_params,
)
from app.integrations.notion.tools._helpers import (
    build_tool,
    encode_error,
    encode_result,
    missing_token_error,
    require_token,
)

# Default page size for search / list endpoints — Notion's max is 100;
# 10 keeps the response token-efficient for normal use.
DEFAULT_SEARCH_PAGE_SIZE = 10
MAX_SEARCH_PAGE_SIZE = 100

# Recursion ceiling for ``notion_file_tree``: stops a malformed tree
# (or an adversarial workspace with cycles) from looping forever.
FILE_TREE_MAX_DEPTH = 6


def make_notion_search_tool(ctx: ToolContext) -> AgentTool:
    """Full-text search across the connected workspace."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        query = str(params.get("query") or "")
        page_size = min(
            int(params.get("page_size") or DEFAULT_SEARCH_PAGE_SIZE),
            MAX_SEARCH_PAGE_SIZE,
        )

        async def _do() -> Any:
            args = [
                "api",
                "v1/search",
                *format_query_params({"query": query, "page_size": str(page_size)}),
            ]
            return await call_ntn_json(args, token=token)

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_search",
                operation="search",
                request={"query": query, "page_size": page_size},
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_search",
        description=(
            "Search the connected Notion workspace by query string. Returns "
            "matching pages and databases ranked by relevance. Use this to "
            "locate a page before reading or editing it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query.",
                },
                "page_size": {
                    "type": "integer",
                    "description": (
                        f"Max results (1-{MAX_SEARCH_PAGE_SIZE}). "
                        f"Default {DEFAULT_SEARCH_PAGE_SIZE}."
                    ),
                    "minimum": 1,
                    "maximum": MAX_SEARCH_PAGE_SIZE,
                    "default": DEFAULT_SEARCH_PAGE_SIZE,
                },
            },
            "required": ["query"],
        },
        execute=execute,
    )


def make_notion_read_tool(ctx: ToolContext) -> AgentTool:
    """Return a page's block tree as raw Notion JSON.

    Prefer ``notion_read_markdown`` for most agent tasks — the markdown
    form is dramatically smaller and easier for the LLM to consume.
    This raw shape exists for callers that need block-level metadata.
    """
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        if not page_id:
            return encode_error("page_id is required")

        async def _do() -> Any:
            return await call_ntn_json(["api", f"v1/blocks/{page_id}/children"], token=token)

        try:
            result = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_read",
                operation="read",
                request={"page_id": page_id},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result(result)

    return build_tool(
        name="notion_read",
        description=(
            "Return the block tree of a Notion page as Notion API JSON. "
            "Prefer notion_read_markdown unless you specifically need raw "
            "block metadata (block types, formatting flags, child counts)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The Notion page ID (UUID).",
                },
            },
            "required": ["page_id"],
        },
        execute=execute,
    )


def make_notion_read_markdown_tool(ctx: ToolContext) -> AgentTool:
    """Return a page rendered as Markdown via ``ntn pages get``."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        page_id = str(params.get("page_id") or "")
        if not page_id:
            return encode_error("page_id is required")

        async def _do() -> Any:
            return await call_ntn_text(["pages", "get", page_id], token=token)

        try:
            markdown = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_read_markdown",
                operation="read",
                request={"page_id": page_id},
                page_id=page_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return json.dumps({"page_id": page_id, "markdown": markdown})

    return build_tool(
        name="notion_read_markdown",
        description=(
            "Render a Notion page as Markdown. The preferred read path for "
            "agents: smaller, structured, and trivially patched back with "
            "notion_update_markdown."
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The Notion page ID (UUID).",
                },
            },
            "required": ["page_id"],
        },
        execute=execute,
    )


def make_notion_file_tree_tool(ctx: ToolContext) -> AgentTool:
    """Walk a page's child hierarchy and return a flat title/id list.

    Composite — calls ``v1/blocks/<id>/children`` recursively up to
    :data:`FILE_TREE_MAX_DEPTH` levels.  Used for "give me a map of
    this section before I dive in" prompts.
    """
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        root_id = str(params.get("page_id") or "")
        max_depth = min(
            int(params.get("max_depth") or FILE_TREE_MAX_DEPTH),
            FILE_TREE_MAX_DEPTH,
        )
        if not root_id:
            return encode_error("page_id is required")

        async def _do() -> Any:
            return await _walk_children(token, root_id, max_depth, 0)

        try:
            tree = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name="notion_file_tree",
                operation="read",
                request={"page_id": root_id, "max_depth": max_depth},
                page_id=root_id,
                func=_do,
            )
        except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return encode_error(str(exc))
        return encode_result({"root": root_id, "tree": tree})

    return build_tool(
        name="notion_file_tree",
        description=(
            "Return a recursive title/id tree of a page's child pages, up "
            f"to {FILE_TREE_MAX_DEPTH} levels deep. Useful for orienting "
            "before deeper reads."
        ),
        parameters={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "Root page ID.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": (
                        f"Recursion ceiling (1-{FILE_TREE_MAX_DEPTH}). Lower values run faster."
                    ),
                    "minimum": 1,
                    "maximum": FILE_TREE_MAX_DEPTH,
                    "default": FILE_TREE_MAX_DEPTH,
                },
            },
            "required": ["page_id"],
        },
        execute=execute,
    )


async def _walk_children(
    token: str, page_id: str, max_depth: int, current_depth: int
) -> list[dict[str, Any]]:
    """Recursively gather child-page summaries under ``page_id``."""
    if current_depth >= max_depth:
        return []
    response = await call_ntn_json(["api", f"v1/blocks/{page_id}/children"], token=token)
    if not isinstance(response, dict):
        return []
    nodes: list[dict[str, Any]] = []
    for block in response.get("results", []) or []:
        if not isinstance(block, dict) or block.get("type") != "child_page":
            continue
        child_id = block.get("id") or ""
        title = ""
        child_page = block.get("child_page")
        if isinstance(child_page, dict):
            title = str(child_page.get("title") or "")
        nodes.append(
            {
                "id": child_id,
                "title": title,
                "children": await _walk_children(token, child_id, max_depth, current_depth + 1),
            }
        )
    return nodes
