"""Local-markdown <-> Notion sync tool.

``notion_sync`` reads a Markdown file from the workspace, looks at its
YAML frontmatter for a ``notion_id`` reference, then either pushes the
local content to Notion or pulls Notion's content into the file based
on the ``direction`` parameter.  The simplification vs openclaw-notion
is intentional: we surface the directional intent as an explicit
parameter rather than auto-detecting via mtime comparisons, which
agents handle more reliably with a small extra argument.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio

from app.core.agent_loop.types import AgentTool
from app.core.plugins.types import ToolContext
from app.integrations.notion.audit import with_audit
from app.integrations.notion.ntn_client import NtnError, call_ntn_text
from app.integrations.notion.tools._helpers import (
    build_tool,
    encode_error,
    encode_result,
    missing_token_error,
    require_token,
)

DIRECTION_PUSH = "push"
DIRECTION_PULL = "pull"
VALID_DIRECTIONS = (DIRECTION_PUSH, DIRECTION_PULL)

# Sentinel frontmatter delimiter line.
_FRONTMATTER_FENCE = "---"


def make_notion_sync_tool(ctx: ToolContext) -> AgentTool:
    """Push or pull a workspace markdown file against a Notion page."""
    token = require_token(ctx)

    async def execute(_tool_call_id: str, params: dict[str, Any]) -> str:
        if token is None:
            return missing_token_error()
        rel_path = str(params.get("path") or "")
        direction = str(params.get("direction") or "").strip().lower()
        if not rel_path or direction not in VALID_DIRECTIONS:
            return encode_error("path and direction (push|pull) are required")

        try:
            target = _safe_workspace_path(ctx.workspace_root, rel_path)
        except ValueError as exc:
            return encode_error(str(exc))

        if direction == DIRECTION_PUSH and not await anyio.Path(target).exists():
            return encode_error(f"path not found: {rel_path}")

        if direction == DIRECTION_PUSH:
            return await _do_push(ctx, token, target, rel_path)
        return await _do_pull(ctx, token, target, rel_path, params)

    return build_tool(
        name="notion_sync",
        description=(
            "Sync a Markdown file in the workspace with a Notion page. "
            "`direction=push` writes local markdown to Notion (page id read "
            "from `notion_id` in YAML frontmatter). `direction=pull` reads "
            "Notion's current markdown into the local file (specify "
            "`page_id` if no frontmatter exists yet)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative path to the Markdown file.",
                },
                "direction": {
                    "type": "string",
                    "enum": list(VALID_DIRECTIONS),
                    "description": "Whether to push local -> Notion or pull Notion -> local.",
                },
                "page_id": {
                    "type": "string",
                    "description": (
                        "Page UUID. Required when pulling into a file with no "
                        "frontmatter; otherwise read from `notion_id` in frontmatter."
                    ),
                },
            },
            "required": ["path", "direction"],
        },
        execute=execute,
    )


def _safe_workspace_path(root: Path, rel_path: str) -> Path:
    """Resolve ``rel_path`` under ``root`` and reject traversal."""
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("path must stay inside the workspace") from exc
    return candidate


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Pull a minimal ``key: value`` frontmatter block out of ``content``.

    Avoids a YAML dep — the only field we read is ``notion_id``, so a
    line-by-line key/value scan is sufficient and predictable.
    Returns ``(frontmatter, body)``.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, content
    fm: dict[str, str] = {}
    body_start: int | None = None
    for idx, raw in enumerate(lines[1:], start=1):
        if raw.strip() == _FRONTMATTER_FENCE:
            body_start = idx + 1
            break
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        fm[key.strip()] = value.strip()
    if body_start is None:
        return {}, content
    return fm, "\n".join(lines[body_start:])


def _serialise_frontmatter(fm: dict[str, str], body: str) -> str:
    """Inverse of :func:`_parse_frontmatter`."""
    if not fm:
        return body
    lines = [_FRONTMATTER_FENCE]
    lines.extend(f"{k}: {v}" for k, v in fm.items())
    lines.append(_FRONTMATTER_FENCE)
    lines.append(body)
    return "\n".join(lines)


async def _do_push(ctx: ToolContext, token: str, target: Path, rel_path: str) -> str:
    """Push local markdown body to its Notion page."""
    content = await anyio.Path(target).read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(content)
    page_id = fm.get("notion_id") or ""
    if not page_id:
        return encode_error("no notion_id in frontmatter; create the page first with notion_create")

    async def _do() -> Any:
        text = await call_ntn_text(["pages", "update", page_id, "--content", body], token=token)
        return {"output": text, "page_id": page_id, "path": rel_path}

    try:
        result = await with_audit(
            workspace_id=ctx.workspace_id,
            tool_name="notion_sync",
            operation="write",
            request={"path": rel_path, "direction": DIRECTION_PUSH},
            page_id=page_id,
            func=_do,
        )
    except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return encode_error(str(exc))
    return encode_result(result)


async def _do_pull(
    ctx: ToolContext,
    token: str,
    target: Path,
    rel_path: str,
    params: dict[str, Any],
) -> str:
    """Pull a Notion page's markdown into the local file."""
    explicit_page_id = str(params.get("page_id") or "").strip()
    existing_fm: dict[str, str] = {}
    apath = anyio.Path(target)
    if await apath.exists():
        existing_fm, _ = _parse_frontmatter(await apath.read_text(encoding="utf-8"))
    page_id = explicit_page_id or existing_fm.get("notion_id") or ""
    if not page_id:
        return encode_error("page_id is required when no notion_id frontmatter exists")

    async def _do() -> Any:
        markdown = await call_ntn_text(["pages", "get", page_id], token=token)
        fm = dict(existing_fm) if existing_fm else {}
        fm["notion_id"] = page_id
        await anyio.Path(target.parent).mkdir(parents=True, exist_ok=True)
        await apath.write_text(_serialise_frontmatter(fm, markdown), encoding="utf-8")
        stat = await apath.stat()
        return {"page_id": page_id, "path": rel_path, "bytes": stat.st_size}

    try:
        result = await with_audit(
            workspace_id=ctx.workspace_id,
            tool_name="notion_sync",
            operation="read",
            request={"path": rel_path, "direction": DIRECTION_PULL},
            page_id=page_id,
            func=_do,
        )
    except (NtnError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return encode_error(str(exc))
    return encode_result(result)
