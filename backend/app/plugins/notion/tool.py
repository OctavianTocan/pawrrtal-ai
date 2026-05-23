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
from typing import Any

from app.core.agent_loop.display import ToolDisplay
from app.core.agent_loop.types import AgentTool
from app.core.keys import resolve_api_key
from app.core.plugins.types import ToolContext
from app.plugins.notion.audit import with_audit
from app.plugins.notion.display import _format_ntn_display
from app.plugins.notion.ntn_client import NtnError, call_ntn

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
