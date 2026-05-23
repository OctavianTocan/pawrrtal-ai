"""Single ``ntn`` tool that proxies to the official Notion CLI.

The plugin previously shipped eighteen narrow tools (``notion_search``,
``notion_read``, ``notion_create``, …) that each shelled out to one
specific ``ntn`` subcommand with hand-rolled parameter schemas.  In
practice the agent didn't need the wrappers: ``ntn`` already exposes
the entire Notion API as a discoverable CLI, and the wrappers were
both lossy (the agent couldn't reach subcommands we hadn't pre-wired)
and bug-prone (every wrapper had its own argument shaping that could
drift from the CLI).

Now there is exactly one tool — ``ntn`` — that accepts an arbitrary
arg list and pipes the resulting stdout / stderr back to the agent.
Token isolation and audit logging stay the same: every call still
goes through :mod:`ntn_client` (workspace-scoped ``NOTION_API_TOKEN``,
ephemeral ``HOME``) and is recorded to ``notion_operation_logs`` so
operators can audit what the agent ran.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.agent_loop.display import ToolDisplay, ToolDisplayPayload
from app.core.agent_loop.types import AgentTool
from app.core.keys import resolve_api_key
from app.core.plugins.types import ToolContext
from app.plugins.notion.audit import with_audit
from app.plugins.notion.ntn_client import NtnError, call_ntn

# Match 32-character hex strings with or without dashes
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}\b"
)

NOTION_API_KEY_NAME = "NOTION_API_KEY"

# Operation tag stored on every audit row; coarser than ``tool_name`` so
# legacy ``notion_logs_read`` queries that grouped by operation keep
# returning useful buckets after the consolidation.
NTN_OPERATION = "cli"

NTN_TOOL_NAME = "ntn"

NTN_TOOL_DESCRIPTION = (
    "Run the official Notion CLI (`ntn`). Use this as your one entry point "
    "for everything Notion-related — search, reading pages, creating pages, "
    "updating content, querying databases, posting comments, archiving, "
    "etc. `args` is the argument list passed straight to the binary (no "
    "shell, no need to prefix `ntn` yourself). The workspace's "
    "`NOTION_API_KEY` is injected for you.\n"
    "\n"
    "Common subcommands (each arg is a separate `args` element; do not "
    "wrap values in shell quotes — there is no shell):\n"
    '  • `args = ["api", "<path>"]` — call the Notion HTTP API. Add '
    '`"-X", "PATCH"` / `"-X", "DELETE"` / `"-X", "POST"` for '
    'non-GET methods, `"-d", "<raw json>"` for a body, and '
    '`"key==value"` for query-string params.\n'
    '  • `args = ["pages", "get", "<page_id>"]` — return the page '
    "rendered as Markdown.\n"
    '  • `args = ["pages", "create", "--parent", "page:<parent_id>",'
    ' "--title", "<t>", "--content", "<md>"]` — create a new page '
    "from Markdown.\n"
    '  • `args = ["pages", "update", "<page_id>", "--content", '
    '"<md>"]` — replace a page\'s body with new Markdown.\n'
    '  • `args = ["--help"]` / `args = ["<command>", "--help"]` — '
    "discover everything else.\n"
    "\n"
    'Return value is JSON: `{"stdout": str, "stderr": str}` on '
    'success, `{"error": str, "returncode": int}` on non-zero exit, '
    'and `{"error": str}` on configuration/timeout failures. Parse '
    "`stdout` yourself — most commands return JSON, but `pages get` / "
    "`pages create` return Markdown."
)


MIN_ARGS_FOR_SUBCMD = 2
ID_DISPLAY_LENGTH = 8
TEXT_TRUNCATE_LENGTH = 20


def _format_api_path(path: str) -> str:
    """Format and truncate UUIDs in raw API paths."""
    match = UUID_PATTERN.search(path)
    if match:
        uuid_str = match.group(0)
        clean_uuid = uuid_str.replace("-", "")
        display_id = clean_uuid[:ID_DISPLAY_LENGTH]
        return path.replace(uuid_str, f"{display_id}...")
    return path


def _parse_pages_create(cmd_args: list[str]) -> ToolDisplayPayload:
    title = ""
    try:
        for flag in ("--title", "-t"):
            if flag in cmd_args:
                idx = cmd_args.index(flag)
                if idx + 1 < len(cmd_args):
                    title = cmd_args[idx + 1]
                    break
            inline_match = next((arg for arg in cmd_args if arg.startswith(f"{flag}=")), None)
            if inline_match:
                title = inline_match.split("=", 1)[1]
                break
    except (ValueError, IndexError):
        pass
    if title:
        title = title.strip("'\"")
    display_title = (
        f' "{title[:TEXT_TRUNCATE_LENGTH]}..."'
        if len(title) > TEXT_TRUNCATE_LENGTH
        else f' "{title}"'
        if title
        else ""
    )
    return ToolDisplayPayload(
        present=f"Creating Notion page{display_title}...",
        compact=f"Created Notion page{display_title}",
        icon="📝",
    )


def _parse_pages_update_append(subcmd: str, page_id: str) -> ToolDisplayPayload:
    display_id = page_id[:ID_DISPLAY_LENGTH] if len(page_id) > ID_DISPLAY_LENGTH else page_id
    suffix = f" {display_id}" if display_id else ""
    if subcmd == "update":
        return ToolDisplayPayload(
            present=f"Updating Notion page{suffix}...",
            compact=f"Updated Notion page{suffix}",
            icon="✏️",
        )
    return ToolDisplayPayload(
        present=f"Appending to Notion page{suffix}...",
        compact=f"Appended to Notion page{suffix}",
        icon="📝",
    )


def _parse_pages_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    """Parse pages command arguments."""
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "pages":
        return None

    subcmd = cmd_args[1]
    if subcmd == "get":
        page_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        display_id = page_id[:ID_DISPLAY_LENGTH] if len(page_id) > ID_DISPLAY_LENGTH else page_id
        suffix = f" {display_id}" if display_id else ""
        return ToolDisplayPayload(
            present=f"Reading Notion page{suffix}...",
            compact=f"Read Notion page{suffix}",
            icon="📖",
        )
    if subcmd == "list":
        return ToolDisplayPayload(
            present="Listing Notion pages...",
            compact="Listed Notion pages",
            icon="📖",
        )
    if subcmd == "create":
        return _parse_pages_create(cmd_args)

    if subcmd in ("update", "append"):
        page_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        return _parse_pages_update_append(subcmd, page_id)

    return None


def _parse_databases_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    """Parse databases command arguments."""
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "databases":
        return None

    subcmd = cmd_args[1]
    if subcmd == "query":
        db_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        display_id = db_id[:ID_DISPLAY_LENGTH] if len(db_id) > ID_DISPLAY_LENGTH else db_id
        suffix = f" {display_id}" if display_id else ""
        return ToolDisplayPayload(
            present=f"Querying Notion database{suffix}...",
            compact=f"Queried Notion database{suffix}",
            icon="🔍",
        )
    if subcmd == "list":
        return ToolDisplayPayload(
            present="Listing Notion databases...",
            compact="Listed Notion databases",
            icon="🔍",
        )
    return None


def _parse_api_databases(cmd_args: list[str], path: str) -> ToolDisplayPayload:
    is_query = "query" in path.lower() or any("query" in arg.lower() for arg in cmd_args)
    db_id = ""
    parts = [p for p in path.split("/") if p]
    try:
        db_idx = parts.index("databases")
        if db_idx + 1 < len(parts):
            db_id = parts[db_idx + 1]
    except ValueError:
        pass

    display_id = db_id[:ID_DISPLAY_LENGTH] if len(db_id) > ID_DISPLAY_LENGTH else db_id
    suffix = f" {display_id}" if display_id else ""

    if is_query:
        return ToolDisplayPayload(
            present=f"Querying Notion database{suffix}...",
            compact=f"Queried Notion database{suffix}",
            icon="🔍",
        )
    return ToolDisplayPayload(
        present=f"Reading Notion database schema{suffix}...",
        compact=f"Read Notion database schema{suffix}",
        icon="🗂️",
    )


def _parse_api_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    """Parse raw API command arguments."""
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "api":
        return None

    if cmd_args[1] == "ls":
        return ToolDisplayPayload(
            present="Listing Notion API endpoints...",
            compact="Listed Notion API endpoints",
            icon="📋",
        )

    path = cmd_args[1].split("?")[0]
    display_path = _format_api_path(path)

    if "search" in path:
        return ToolDisplayPayload(
            present="Searching Notion...",
            compact="Searched Notion",
            icon="🔍",
        )
    if "databases" in path:
        return _parse_api_databases(cmd_args, path)

    if "pages" in path:
        is_write = any(val in "".join(cmd_args).lower() for val in ["post", "patch", "delete"])
        return ToolDisplayPayload(
            present=f"Updating Notion page ({display_path})...."
            if is_write
            else f"Reading Notion page ({display_path})...",
            compact=f"Updated Notion page ({display_path})"
            if is_write
            else f"Read Notion page ({display_path})",
            icon="📝" if is_write else "📖",
        )
    return ToolDisplayPayload(
        present=f"Calling Notion API ({display_path})...",
        compact=f"Called Notion API ({display_path})",
        icon="📓",
    )


def _parse_help_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    """Parse help command arguments."""
    if not any(h in cmd_args for h in ("--help", "-h")):
        return None

    subcommands = [a for a in cmd_args if not a.startswith("-")]
    if subcommands:
        target = subcommands[0]
        return ToolDisplayPayload(
            present=f"Displaying help for Notion {target}...",
            compact=f"Displayed help for Notion {target}",
            icon="ℹ️",  # noqa: RUF001
        )
    return ToolDisplayPayload(
        present="Displaying Notion help...",
        compact="Displayed Notion help",
        icon="ℹ️",  # noqa: RUF001
    )


def _parse_doctor_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    """Parse doctor diagnostic command."""
    if not cmd_args or cmd_args[0] != "doctor":
        return None
    return ToolDisplayPayload(
        present="Running Notion diagnostics...",
        compact="Ran Notion diagnostics",
        icon="🩺",
    )


def _format_ntn_display(arguments: dict[str, Any]) -> ToolDisplayPayload:
    """Format Notion tool calls dynamically for user-facing UI."""
    raw_args = arguments.get("args")
    fallback = ToolDisplayPayload(
        present="Running Notion command...",
        compact="Notion command",
        icon="📓",
    )

    cmd_args = []
    if isinstance(raw_args, str):
        cmd_args = [raw_args.strip()]
    elif isinstance(raw_args, list):
        cmd_args = [str(a).strip() for a in raw_args]

    if not cmd_args:
        return fallback

    # Filter out global flags preceding the subcommand
    global_flags = {"--json", "--verbose", "-v", "--no-color"}
    filtered_args = [a for a in cmd_args if a not in global_flags]

    if not filtered_args:
        # If there are only global flags, treat it as help or fallback
        help_payload = _parse_help_command(cmd_args)
        if help_payload:
            return help_payload
        return fallback

    # Flatten nested branches by using 'or' evaluation
    payload = (
        _parse_pages_command(filtered_args)
        or _parse_databases_command(filtered_args)
        or _parse_api_command(filtered_args)
        or _parse_help_command(cmd_args)
        or _parse_doctor_command(filtered_args)
    )

    if not payload and "search" in filtered_args:
        payload = ToolDisplayPayload(
            present="Searching Notion...",
            compact="Searched Notion",
            icon="🔍",
        )

    if payload is None:
        joined = " ".join(cmd_args)
        display_cmd = (
            f" '{joined[:TEXT_TRUNCATE_LENGTH]}...'"
            if len(joined) > TEXT_TRUNCATE_LENGTH
            else f" '{joined}'"
        )
        payload = ToolDisplayPayload(
            present=f"Running Notion command{display_cmd}...",
            compact=f"Ran Notion command{display_cmd}",
            icon="📓",
        )

    # Append stdin indicator if provided (simplified single if)
    if bool(arguments.get("stdin")) and not payload["present"].endswith(" (piped stdin)..."):
        pres = payload["present"]
        if pres.endswith("..."):
            pres = pres[:-3]
        payload["present"] = f"{pres} (piped stdin)..."
        payload["compact"] = f"{payload['compact']} (piped stdin)"

    return payload


def make_ntn_tool(ctx: ToolContext) -> AgentTool:
    """Build the single ``ntn`` proxy tool bound to ``ctx``."""

    async def execute(_tool_call_id: str, **kwargs: object) -> str:
        token = resolve_api_key(ctx.workspace_root, NOTION_API_KEY_NAME)
        if not token:
            return _encode_error(
                "Notion is not configured for this workspace. "
                "Add a NOTION_API_KEY in Settings → Workspace."
            )

        try:
            normalised_args = _coerce_args(kwargs.get("args"))
        except (TypeError, ValueError) as exc:
            return _encode_error(str(exc))

        stdin_bytes = _coerce_stdin(kwargs.get("stdin"))

        async def _do() -> dict[str, str]:
            result = await call_ntn(normalised_args, token=token, stdin=stdin_bytes)
            return {
                "stdout": result.stdout.decode(errors="replace"),
                "stderr": result.stderr.decode(errors="replace"),
            }

        try:
            payload = await with_audit(
                workspace_id=ctx.workspace_id,
                tool_name=NTN_TOOL_NAME,
                operation=NTN_OPERATION,
                request={
                    "args": normalised_args,
                    "has_stdin": stdin_bytes is not None,
                },
                func=_do,
            )
        except NtnError as exc:
            return json.dumps(
                {
                    "error": f"ntn exited {exc.returncode}: {exc.stderr.strip()[:500]}",
                    "returncode": exc.returncode,
                }
            )
        except (OSError, TimeoutError) as exc:
            return _encode_error(str(exc))

        return json.dumps(payload, ensure_ascii=False)

    return AgentTool(
        name=NTN_TOOL_NAME,
        description=NTN_TOOL_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Argument list passed to the `ntn` binary, "
                        "excluding the program name. Example: "
                        '["pages", "get", "<page_id>"].'
                    ),
                    "minItems": 1,
                },
                "stdin": {
                    "type": "string",
                    "description": (
                        "Optional UTF-8 text piped to ntn's stdin. Used by "
                        "subcommands like `ntn files create` that accept "
                        "piped content."
                    ),
                },
            },
            "required": ["args"],
        },
        execute=execute,
        display=ToolDisplay(
            icon="📓",
            label="Notion",
            formatter=_format_ntn_display,
        ),
    )


def _coerce_args(raw: object) -> list[str]:
    """Validate ``args`` and return a list of strings.

    Models occasionally collapse a single-element array into a bare
    string for array-typed fields — that one shape is forgiven by
    wrapping in a single-item list.  Anything else (numbers, dicts,
    nested arrays) is rejected explicitly so the agent gets a clear
    validation error instead of an opaque CLI failure from
    ``str(dict)`` producing Python repr output that the ``ntn``
    binary can't parse.
    """
    if isinstance(raw, str):
        items: list[Any] = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        raise TypeError("`args` must be a non-empty list of strings.")

    if not items:
        raise ValueError("`args` must be a non-empty list of strings.")

    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise TypeError(
                f"`args[{index}]` must be a string (got {type(item).__name__}). "
                "If you need to pass a JSON body, serialise it to a string "
                "first and place it after the corresponding `-d` flag."
            )
    return list(items)


def _coerce_stdin(raw: object) -> bytes | None:
    """Return UTF-8 bytes for ``stdin``, or ``None`` when unset."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bytes):
        return raw
    return str(raw).encode("utf-8")


def _encode_error(message: str) -> str:
    """Render a stable JSON error envelope for the agent."""
    return json.dumps({"error": message})
