"""Agent tools for simple workspace-local Beans tasks."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess  # nosec B404 - canonical beans CLI invocation uses argv lists, never shell.
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.agents.tool_capabilities.display import make_tool_display, summarize_title
from app.agents.tool_capabilities.errors import ToolError, ToolErrorCode
from app.agents.types import AgentTool
from app.plugins.tool_context import ToolContext

_BEANS_DIR = ".beans"
_BEANS_BINARY = "beans"
_BEANS_TIMEOUT_SECONDS = 5
_UPDATE_BASE_ARG_COUNT = 2
_VALID_STATUSES = frozenset({"draft", "todo", "in-progress", "in-review", "completed", "scrapped"})

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Bean:
    """One parsed `.beans/*.md` task file."""

    bean_id: str
    path: Path
    meta: dict[str, object]
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
        before = {bean.bean_id for bean in _load_beans(ctx.workspace_root)}
        args = ["create", title, "-s", status, "-p", priority, "-t", task_type]
        if body:
            args.extend(["-d", body])
        try:
            stdout = await _run_beans(ctx.workspace_root, args)
        except ToolError as exc:
            return exc.render()
        created = [bean for bean in _load_beans(ctx.workspace_root) if bean.bean_id not in before]
        if len(created) == 1:
            return f"Created bean {created[0].bean_id}: {_meta_text(created[0], 'title', title)}"
        return stdout or "Created bean."

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
                    "description": "draft, todo, in-progress, in-review, completed, or scrapped.",
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
        try:
            status_filter = _optional_status(kwargs.get("status"))
        except ToolError as exc:
            return exc.render()
        beans = _load_beans(ctx.workspace_root)
        rows = []
        for bean in beans:
            status = _meta_text(bean, "status", "todo")
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
        args = ["update", bean.bean_id]
        for key in ("title", "priority", "type"):
            value = kwargs.get(key)
            if isinstance(value, str) and value.strip():
                args.extend(_field_args(key, value.strip()))
        if kwargs.get("status"):
            try:
                args.extend(["-s", _status(kwargs["status"])])
            except ToolError as exc:
                return exc.render()
        body_file_text = None
        if isinstance(kwargs.get("body"), str):
            body_file_text = kwargs["body"].strip()
        if isinstance(kwargs.get("body_append"), str) and kwargs["body_append"].strip():
            args.extend(["--body-append", kwargs["body_append"].strip()])
        if len(args) == _UPDATE_BASE_ARG_COUNT and body_file_text is None:
            return f"No bean changes requested for {bean.bean_id}."
        try:
            stdout = await _run_beans(ctx.workspace_root, args, body_file_text=body_file_text)
        except ToolError as exc:
            return exc.render()
        return stdout or f"Updated bean {bean.bean_id}."

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
        try:
            stdout = await _run_beans(
                ctx.workspace_root, ["update", bean.bean_id, "-s", "completed"]
            )
        except ToolError as exc:
            return exc.render()
        return stdout or f"Completed bean {bean.bean_id}."

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
    beans: list[Bean] = []
    for path in root.glob("*.md"):
        try:
            beans.append(_read_bean(path))
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("BEANS_TASKS_SKIP_INVALID_FILE path=%s error=%s", path, exc)
    return sorted(beans, key=lambda bean: bean.bean_id)


def _find_bean(workspace_root: Path, query: str) -> Bean:
    needle = query.casefold()
    matches = [
        bean
        for bean in _load_beans(workspace_root)
        if needle in bean.bean_id.casefold() or needle in _meta_text(bean, "title", "").casefold()
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


def _split_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    _, rest = raw.split("---\n", 1)
    head, marker, body = rest.partition("\n---\n")
    if not marker:
        return {}, raw
    parsed = yaml.safe_load(head)
    if not isinstance(parsed, dict):
        return {}, body
    meta = {str(key): value for key, value in parsed.items()}
    return meta, body


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


def _optional_status(value: object) -> str:
    raw = str(value or "").strip()
    return _status(raw) if raw else ""


def _bean_id_from_path(path: Path) -> str:
    return path.stem.split("--", 1)[0]


def _format_row(bean: Bean) -> str:
    title = _meta_text(bean, "title", "(untitled)")
    status = _meta_text(bean, "status", "todo")
    priority = _meta_text(bean, "priority", "normal")
    return f"- {bean.bean_id} [{status}/{priority}] {title}"


def _meta_text(bean: Bean, key: str, fallback: str) -> str:
    value = bean.meta.get(key)
    if value is None:
        return fallback
    return str(value)


def _field_args(key: str, value: str) -> list[str]:
    if key == "title":
        return ["--title", value]
    if key == "priority":
        return ["-p", value]
    return ["-t", value]


async def _run_beans(
    workspace_root: Path,
    args: list[str],
    *,
    body_file_text: str | None = None,
) -> str:
    binary = shutil.which(_BEANS_BINARY)
    if binary is None:
        raise ToolError(ToolErrorCode.NOT_FOUND, "beans CLI is not installed or not on PATH.")

    body_file_path = _write_body_file(body_file_text)
    cli_args = [binary, *args]
    if body_file_path is not None:
        cli_args.extend(["--body-file", str(body_file_path)])

    stdout_path = _temp_output_path("stdout")
    stderr_path = _temp_output_path("stderr")
    stdout_file = stdout_path.open("wb")
    stderr_file = stderr_path.open("wb")
    process_finished = False
    try:
        # Only process creation is synchronous; waiting below is async polling.
        process = subprocess.Popen(  # noqa: ASYNC220,S603  # nosec B603
            cli_args,
            cwd=workspace_root,
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        stdout_file.close()
        stderr_file.close()
        if not await _wait_for_process(process, timeout_seconds=_BEANS_TIMEOUT_SECONDS):
            process.kill()
            await _wait_for_process(process, timeout_seconds=1)
            raise ToolError(ToolErrorCode.IO_ERROR, "beans CLI timed out.")
        process_finished = True
    except OSError as exc:
        raise ToolError(ToolErrorCode.IO_ERROR, f"beans CLI failed to start: {exc}") from exc
    finally:
        if not stdout_file.closed:
            stdout_file.close()
        if not stderr_file.closed:
            stderr_file.close()
        if body_file_path is not None:
            body_file_path.unlink(missing_ok=True)
        if not process_finished:
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)

    stdout = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
    stdout_path.unlink(missing_ok=True)
    stderr_path.unlink(missing_ok=True)
    if process.returncode != 0:
        detail = stderr or stdout or f"exit {process.returncode}"
        raise ToolError(ToolErrorCode.IO_ERROR, f"{_beans_action(args)} failed: {detail}")
    return stdout


async def _wait_for_process(process: subprocess.Popen[bytes], *, timeout_seconds: int) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while process.poll() is None:
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(0.05)
    return True


def _write_body_file(body_file_text: str | None) -> Path | None:
    if body_file_text is None:
        return None
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="pawrrtal-bean-body-",
        suffix=".md",
        delete=False,
    ) as body_file:
        body_file.write(body_file_text)
        return Path(body_file.name)


def _temp_output_path(stream_name: str) -> Path:
    with tempfile.NamedTemporaryFile(
        "wb",
        prefix=f"pawrrtal-beans-{stream_name}-",
        delete=False,
    ) as output_file:
        return Path(output_file.name)


def _beans_action(args: list[str]) -> str:
    if args:
        return f"beans {args[0]}"
    return "beans"
