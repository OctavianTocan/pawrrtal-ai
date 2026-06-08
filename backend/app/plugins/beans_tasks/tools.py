"""Agent tools for simple workspace-local Beans tasks."""

from __future__ import annotations

import datetime as dt
import re
import secrets
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext
from app.tools.display import make_tool_display, summarize_title
from app.tools.errors import ToolError, ToolErrorCode

_BEANS_DIR = ".beans"
_ID_ALPHABET = string.ascii_lowercase + string.digits
_VALID_STATUSES = frozenset({"todo", "in-progress", "completed", "scrapped"})


@dataclass(frozen=True, slots=True)
class Bean:
    """One parsed `.beans/*.md` task file."""

    bean_id: str
    path: Path
    meta: dict[str, str]
    body: str


def make_beans_create_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``beans_create`` tool."""

    async def execute(_tool_call_id: str, **kwargs: Any) -> str:
        try:
            title = _required_text(kwargs, "title")
            status = _status(kwargs.get("status") or "todo")
        except ToolError as exc:
            return exc.render()
        priority = str(kwargs.get("priority") or "normal").strip() or "normal"
        task_type = str(kwargs.get("type") or "task").strip() or "task"
        body = str(kwargs.get("body") or "").strip()
        bean_id = _new_bean_id()
        path = _beans_root(ctx.workspace_root) / f"{bean_id}--{_slug(title)}.md"
        now = _now()
        meta = {
            "title": title,
            "status": status,
            "type": task_type,
            "priority": priority,
            "created_at": now,
            "updated_at": now,
        }
        _write_bean(path, bean_id=bean_id, meta=meta, body=body)
        return f"Created bean {bean_id}: {title}"

    return AgentTool(
        name="beans_create",
        description="Create a task bean under .beans in the user's workspace.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short task title."},
                "body": {"type": "string", "description": "Optional Markdown body."},
                "status": {
                    "type": "string",
                    "description": "todo, in-progress, completed, or scrapped.",
                },
                "priority": {
                    "type": "string",
                    "description": "Priority label. Defaults to normal.",
                },
                "type": {"type": "string", "description": "Bean type. Defaults to task."},
            },
            "required": ["title"],
        },
        execute=execute,
        display=make_tool_display(
            icon="B",
            label="Beans Create",
            present=lambda args: f"Creating bean: {summarize_title(args.get('title'), 'untitled')}",
            compact=lambda args: f"beans_create({str(args.get('title') or '')[:40]})",
        ),
    )


def make_beans_list_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``beans_list`` tool."""

    async def execute(_tool_call_id: str, **kwargs: Any) -> str:
        include_completed = bool(kwargs.get("include_completed"))
        status_filter = str(kwargs.get("status") or "").strip()
        beans = _load_beans(ctx.workspace_root)
        rows = []
        for bean in beans:
            status = bean.meta.get("status", "todo")
            if status_filter and status != status_filter:
                continue
            if not include_completed and status in {"completed", "scrapped"}:
                continue
            rows.append(_format_row(bean))
        return "\n".join(rows) if rows else "No beans found."

    return AgentTool(
        name="beans_list",
        description="List task beans from .beans in the user's workspace.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Optional exact status filter."},
                "include_completed": {
                    "type": "boolean",
                    "description": "Include completed and scrapped beans.",
                },
            },
            "required": [],
        },
        execute=execute,
        display=make_tool_display(
            icon="B",
            label="Beans List",
            present=lambda _args: "Listing beans",
            compact=lambda _args: "beans_list()",
        ),
    )


def make_beans_update_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``beans_update`` tool."""

    async def execute(_tool_call_id: str, **kwargs: Any) -> str:
        try:
            bean = _find_bean(ctx.workspace_root, _required_text(kwargs, "bean"))
        except ToolError as exc:
            return exc.render()
        meta = dict(bean.meta)
        for key in ("title", "priority", "type"):
            value = kwargs.get(key)
            if isinstance(value, str) and value.strip():
                meta[key] = value.strip()
        if kwargs.get("status"):
            try:
                meta["status"] = _status(kwargs["status"])
            except ToolError as exc:
                return exc.render()
        meta["updated_at"] = _now()
        body = bean.body
        if isinstance(kwargs.get("body"), str):
            body = kwargs["body"].strip()
        if isinstance(kwargs.get("body_append"), str) and kwargs["body_append"].strip():
            body = f"{body.rstrip()}\n\n{kwargs['body_append'].strip()}".strip()
        _write_bean(bean.path, bean_id=bean.bean_id, meta=meta, body=body)
        return f"Updated bean {bean.bean_id}."

    return AgentTool(
        name="beans_update",
        description="Update a task bean by id or title substring.",
        parameters={
            "type": "object",
            "properties": {
                "bean": {"type": "string", "description": "Bean id or title substring."},
                "title": {"type": "string"},
                "status": {"type": "string"},
                "priority": {"type": "string"},
                "type": {"type": "string"},
                "body": {"type": "string"},
                "body_append": {"type": "string"},
            },
            "required": ["bean"],
        },
        execute=execute,
        display=make_tool_display(
            icon="B",
            label="Beans Update",
            present=lambda args: f"Updating bean: {summarize_title(args.get('bean'), 'unknown')}",
            compact=lambda args: f"beans_update({str(args.get('bean') or '')[:40]})",
        ),
    )


def make_beans_complete_tool(ctx: ToolContext) -> AgentTool:
    """Return the workspace-bound ``beans_complete`` tool."""

    async def execute(_tool_call_id: str, **kwargs: Any) -> str:
        try:
            bean = _find_bean(ctx.workspace_root, _required_text(kwargs, "bean"))
        except ToolError as exc:
            return exc.render()
        meta = dict(bean.meta)
        meta["status"] = "completed"
        meta["updated_at"] = _now()
        _write_bean(bean.path, bean_id=bean.bean_id, meta=meta, body=bean.body)
        return f"Completed bean {bean.bean_id}."

    return AgentTool(
        name="beans_complete",
        description="Mark a task bean completed by id or title substring.",
        parameters={
            "type": "object",
            "properties": {
                "bean": {"type": "string", "description": "Bean id or title substring."}
            },
            "required": ["bean"],
        },
        execute=execute,
        display=make_tool_display(
            icon="B",
            label="Beans Complete",
            present=lambda args: f"Completing bean: {summarize_title(args.get('bean'), 'unknown')}",
            compact=lambda args: f"beans_complete({str(args.get('bean') or '')[:40]})",
        ),
    )


def _beans_root(workspace_root: Path) -> Path:
    return workspace_root / _BEANS_DIR


def _load_beans(workspace_root: Path) -> list[Bean]:
    root = _beans_root(workspace_root)
    if not root.exists():
        return []
    return sorted((_read_bean(path) for path in root.glob("*.md")), key=lambda bean: bean.bean_id)


def _find_bean(workspace_root: Path, query: str) -> Bean:
    needle = query.casefold()
    matches = [
        bean
        for bean in _load_beans(workspace_root)
        if needle in bean.bean_id.casefold() or needle in bean.meta.get("title", "").casefold()
    ]
    if not matches:
        raise ToolError(ToolErrorCode.NOT_FOUND, f"No bean matched {query!r}.")
    if len(matches) > 1:
        ids = ", ".join(bean.bean_id for bean in matches[:5])
        raise ToolError(ToolErrorCode.INVALID_PATH, f"Multiple beans matched {query!r}: {ids}.")
    return matches[0]


def _read_bean(path: Path) -> Bean:
    raw = path.read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw)
    return Bean(bean_id=_bean_id_from_path(path), path=path, meta=meta, body=body.strip())


def _split_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    _, rest = raw.split("---\n", 1)
    head, marker, body = rest.partition("\n---\n")
    if not marker:
        return {}, raw
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, body


def _write_bean(path: Path, *, bean_id: str, meta: dict[str, str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"# {bean_id}"]
    lines.extend(f"{key}: {value}" for key, value in meta.items())
    lines.extend(["---", "", body.strip(), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _required_text(kwargs: dict[str, Any], key: str) -> str:
    value = str(kwargs.get(key) or "").strip()
    if not value:
        raise ToolError(ToolErrorCode.INVALID_PATH, f"The {key!r} argument is required.")
    return value


def _status(value: object) -> str:
    status = str(value or "").strip()
    if status not in _VALID_STATUSES:
        raise ToolError(ToolErrorCode.INVALID_PATH, f"Unsupported bean status {status!r}.")
    return status


def _new_bean_id() -> str:
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(4))
    return f"pawrrtal-{suffix}"


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return slug[:70] or "task"


def _bean_id_from_path(path: Path) -> str:
    return path.stem.split("--", 1)[0]


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_row(bean: Bean) -> str:
    title = bean.meta.get("title", "(untitled)")
    status = bean.meta.get("status", "todo")
    priority = bean.meta.get("priority", "normal")
    return f"- {bean.bean_id} [{status}/{priority}] {title}"
