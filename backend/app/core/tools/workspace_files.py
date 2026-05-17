"""Workspace-scoped file tools for the agent loop.

Provides ``read_file``, ``write_file``, and ``list_dir`` as :class:`AgentTool`
instances bound to a specific workspace root directory.  Path traversal is
blocked: any path that resolves outside the workspace root surfaces a
:class:`ToolError` rather than raising, so the agent can read the message
and adjust.

All paths the model passes are interpreted relative to the workspace root.
The agent should treat the root as ``/`` (or ``.``) — this contract is
communicated via the tool descriptions, and the chat router additionally
mentions it in the assembled system prompt when these tools are mounted.

Usage::

    from pathlib import Path
    from app.core.tools.workspace_files import make_workspace_tools

    tools = make_workspace_tools(Path("/data/workspaces/<uuid>"))
    # Pass ``tools`` into AgentContext.tools before calling agent_loop().
"""

from __future__ import annotations

import errno
import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anyio

from app.core.agent_loop.types import AgentTool
from app.core.tools.errors import ToolError, ToolErrorCode

log = logging.getLogger(__name__)

# Maximum bytes read_file will return so the model context doesn't blow up.
_MAX_READ_BYTES = 128_000  # 128 KB
# Maximum number of entries list_dir will return.
_MAX_LIST_ENTRIES = 200
# 1024-byte step we use to step through B / KB / MB / GB labels.
_BYTES_PER_KIB = 1024


# ---------------------------------------------------------------------------
# Forbidden filenames + dangerous file patterns (PR 03)
#
# Lifted verbatim from claude-code-telegram's ``SecurityValidator``
# (``src/security/validators.py:92-132``). Even with the workspace
# sandbox there's no good reason for the agent to read a user's
# ``.env``, SSH key, or private cert — those are credentials that
# should never be in a prompt or a chat-message persistence row.
#
# The permission gate (``governance.permissions``) consults these
# lists on every file-shaped tool call; workspaces that legitimately
# need access to a forbidden filename can opt in via the
# ``WorkspaceContext`` allowlist (PR 06).
# ---------------------------------------------------------------------------

FORBIDDEN_FILENAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".ssh",
        ".aws",
        ".docker",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "shadow",
        "passwd",
        "hosts",
        "sudoers",
        ".bash_history",
        ".zsh_history",
        ".mysql_history",
        ".psql_history",
    }
)

DANGEROUS_FILE_PATTERNS: tuple[str, ...] = (
    r".*\.key$",
    r".*\.pem$",
    r".*\.p12$",
    r".*\.pfx$",
    r".*\.crt$",
    r".*\.cer$",
    r".*_rsa$",
    r".*_dsa$",
    r".*_ecdsa$",
    r".*\.exe$",
    r".*\.dll$",
    r".*\.so$",
    r".*\.dylib$",
    r".*\.bat$",
    r".*\.cmd$",
    r".*\.msi$",
)

DANGEROUS_FILE_PATTERN_REGEXES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in DANGEROUS_FILE_PATTERNS
)


def matches_forbidden_filename(path: str) -> bool:
    """``True`` when ``path`` ends in a forbidden filename or pattern.

    Comparison is on the basename so a forbidden filename anywhere in
    the tree is caught (``logs/.env`` is just as bad as ``./.env``).
    Pattern matching is case-insensitive.
    """
    if not path:
        return False
    basename = Path(path).name.lower()
    if basename in {entry.lower() for entry in FORBIDDEN_FILENAMES}:
        return True
    return any(pattern.match(basename) for pattern in DANGEROUS_FILE_PATTERN_REGEXES)


def is_path_within_workspace(path: str, workspace_root: Path) -> bool:
    """Resolve ``path`` against ``workspace_root`` and confirm containment.

    Mirrors what :func:`_resolve_safe` does but returns a bool instead
    of raising so the permission gate can short-circuit cleanly.
    Treats relative paths as relative to ``workspace_root``; absolute
    paths are resolved as-is and then containment-checked.
    """
    if not path:
        # Empty path == workspace root, which is in-bounds.
        return True
    root_resolved = workspace_root.resolve()
    candidate = Path(path)
    try:
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (root_resolved / path.lstrip("/")).resolve()
    except (OSError, ValueError):
        return False
    # Path-aware containment via ``is_relative_to`` (Python 3.9+) — a
    # plain ``str.startswith`` accepts sibling-directory prefixes
    # (``/data/workspaces/abc`` vs ``/data/workspaces/abcdef``).
    return resolved == root_resolved or resolved.is_relative_to(root_resolved)


def _resolve_safe(root: Path, rel_path: str) -> Path:
    """Resolve *rel_path* relative to *root* and return it if still inside.

    Raises :class:`ToolError` (``OUT_OF_ROOT``) when the resolved path
    escapes the workspace root or cannot be resolved at all.
    """
    try:
        target = (root / rel_path.lstrip("/")).resolve()
    except (OSError, ValueError) as exc:
        raise ToolError(
            ToolErrorCode.INVALID_PATH,
            f"Could not resolve path '{rel_path}': {exc}",
        ) from exc
    # resolve() follows symlinks; check containment via ``is_relative_to``
    # so a sibling directory whose name shares a string prefix with the
    # root (``/data/workspaces/abc`` vs ``/data/workspaces/abcdef``) is
    # still rejected.
    root_resolved = root.resolve()
    if target != root_resolved and not target.is_relative_to(root_resolved):
        raise ToolError(
            ToolErrorCode.OUT_OF_ROOT,
            f"Path '{rel_path}' resolves outside the workspace root.",
        )
    return target


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < _BYTES_PER_KIB:
            return f"{n}{unit}"
        n //= _BYTES_PER_KIB
    return f"{n}TB"


# A workspace tool body receives the resolved-and-checked target path plus
# whatever extra kwargs the schema declares; raising ToolError on failure
# is preferred over returning error strings (the wrapper does that).
WorkspaceToolBody = Callable[..., Awaitable[str]]


def _wrap_workspace_tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    body: WorkspaceToolBody,
    root: Path,
    path_required: bool,
) -> AgentTool:
    """Build an AgentTool that resolves ``path`` safely before calling *body*.

    Centralises the path-traversal check, the ``ToolError`` → string
    translation, and the AgentTool dataclass construction so individual
    tool bodies stay tiny and only encode their own behaviour.
    """

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        raw_path = kwargs.pop("path", None)
        if path_required and not raw_path:
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "The 'path' argument is required.",
            ).render()
        try:
            target = _resolve_safe(root, raw_path or "")
            return await body(target=target, raw_path=raw_path or "", **kwargs)
        except ToolError as err:
            return err.render()
        except OSError as exc:
            return ToolError(
                ToolErrorCode.IO_ERROR,
                f"Filesystem error on '{raw_path}': {exc}",
            ).render()

    return AgentTool(
        name=name,
        description=description,
        parameters=parameters,
        execute=execute,
    )


# ---------------------------------------------------------------------------
# Tool bodies
# ---------------------------------------------------------------------------


def _read_file_sync(target: Path, raw_path: str) -> str:
    if not target.exists():
        raise ToolError(ToolErrorCode.NOT_FOUND, f"'{raw_path}' does not exist.")
    if not target.is_file():
        raise ToolError(
            ToolErrorCode.WRONG_KIND,
            f"'{raw_path}' is a directory, not a file.",
        )
    # Open with ``O_NOFOLLOW`` so a symlink swapped in between the earlier
    # ``resolve()`` containment check and this read can't escape the jail.
    # ``Path.read_bytes`` uses plain ``open()`` which follows symlinks at
    # syscall time, leaving a TOCTOU window the workspace agent could trip
    # accidentally (a stray symlink it wrote earlier in the conversation).
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        # ``ELOOP`` is the canonical "target is a symlink" failure when
        # ``O_NOFOLLOW`` is set; surface it as ``OUT_OF_ROOT`` so the
        # model gets the same shape of error as a traversal attempt.
        if exc.errno == errno.ELOOP:
            raise ToolError(
                ToolErrorCode.OUT_OF_ROOT,
                f"'{raw_path}' is a symlink and cannot be read for safety.",
            ) from exc
        raise
    with os.fdopen(fd, "rb") as fh:
        raw = fh.read(_MAX_READ_BYTES + 1)
    if len(raw) > _MAX_READ_BYTES:
        raw = raw[:_MAX_READ_BYTES]
        suffix = f"\n\n[truncated — file exceeds {_MAX_READ_BYTES // _BYTES_PER_KIB} KB]"
    else:
        suffix = ""
    try:
        return raw.decode("utf-8") + suffix
    except UnicodeDecodeError as exc:
        raise ToolError(
            ToolErrorCode.BINARY_FILE,
            f"'{raw_path}' is a binary file and cannot be read as text.",
        ) from exc


async def _read_file_body(*, target: Path, raw_path: str, **_: Any) -> str:
    return await anyio.to_thread.run_sync(_read_file_sync, target, raw_path)


def _write_file_sync(target: Path, raw_path: str, content: str) -> str:
    if target.is_dir():
        raise ToolError(
            ToolErrorCode.WRONG_KIND,
            f"'{raw_path}' is a directory.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    # Open with ``O_NOFOLLOW`` so a symlink swapped in between
    # ``_resolve_safe`` and this write can't escape the jail. Mirrors the
    # protection ``read_file`` already has — without it, an attacker (or
    # the agent itself, via the ``python`` tool's ``os.symlink``) could
    # plant a symlink inside the workspace pointing at e.g. ``/etc/cron.d``
    # and have us overwrite it.
    encoded = content.encode("utf-8")
    try:
        fd = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o644,
        )
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ToolError(
                ToolErrorCode.OUT_OF_ROOT,
                f"'{raw_path}' is a symlink and cannot be written for safety.",
            ) from exc
        raise
    with os.fdopen(fd, "wb") as fh:
        fh.write(encoded)
    return f"Written {len(content)} characters to '{raw_path}'."


async def _write_file_body(*, target: Path, raw_path: str, content: str = "", **_: Any) -> str:
    return await anyio.to_thread.run_sync(_write_file_sync, target, raw_path, content)


def _list_dir_sync(target: Path, raw_path: str, root: Path) -> str:
    if not target.exists():
        raise ToolError(ToolErrorCode.NOT_FOUND, f"'{raw_path}' does not exist.")
    if not target.is_dir():
        raise ToolError(
            ToolErrorCode.WRONG_KIND,
            f"'{raw_path}' is a file, not a directory. Use read_file to read it.",
        )
    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
    if not entries:
        return f"'{raw_path or '.'}' is empty."

    lines: list[str] = []
    for entry in entries[:_MAX_LIST_ENTRIES]:
        rel = entry.relative_to(root)
        if entry.is_dir():
            lines.append(f"[dir]  {rel}/")
        else:
            size = _fmt_size(entry.stat().st_size)
            lines.append(f"[file] {rel}  ({size})")

    if len(entries) > _MAX_LIST_ENTRIES:
        lines.append(f"... and {len(entries) - _MAX_LIST_ENTRIES} more entries")
    return "\n".join(lines)


async def _list_dir_body(*, target: Path, raw_path: str, root: Path, **_: Any) -> str:
    return await anyio.to_thread.run_sync(_list_dir_sync, target, raw_path, root)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def make_workspace_tools(workspace_root: Path) -> list[AgentTool]:
    """Return a list of file-access AgentTools scoped to *workspace_root*.

    All paths are resolved relative to *workspace_root* and path traversal
    is blocked.  Pass the returned list into ``AgentContext.tools`` before
    calling ``agent_loop()``.

    Args:
        workspace_root: Absolute path to the workspace directory.  Must
            already exist on disk.

    Returns:
        ``[read_file, write_file, list_dir]`` AgentTool instances.
    """
    root = Path(workspace_root).resolve()

    return [
        _wrap_workspace_tool(
            name="read_file",
            description=(
                "Read the text content of a file in the workspace. "
                "Paths are relative to the workspace root. "
                "Binary files and files larger than 128 KB are rejected or truncated."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "File path relative to the workspace root, e.g. 'AGENTS.md' "
                            "or 'memory/2026-05-07.md'."
                        ),
                    }
                },
                "required": ["path"],
            },
            body=_read_file_body,
            root=root,
            path_required=True,
        ),
        _wrap_workspace_tool(
            name="write_file",
            description=(
                "Write text content to a file in the workspace, creating it if it "
                "does not exist and overwriting it if it does. "
                "Parent directories are created automatically. "
                "Paths are relative to the workspace root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to the workspace root.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content to write. Overwrites the existing file.",
                    },
                },
                "required": ["path", "content"],
            },
            body=_write_file_body,
            root=root,
            path_required=True,
        ),
        _wrap_workspace_tool(
            name="list_dir",
            description=(
                "List the contents of a directory in the workspace. "
                "Shows directories with a trailing '/' and files with their sizes. "
                "Call with no path (or empty string) to list the workspace root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory path relative to the workspace root. "
                            "Omit or pass '' to list the root."
                        ),
                    }
                },
                "required": [],
            },
            # list_dir's body needs ``root`` for ``relative_to`` formatting.
            body=lambda target, raw_path, **kw: _list_dir_body(
                target=target, raw_path=raw_path, root=root, **kw
            ),
            root=root,
            path_required=False,
        ),
    ]
