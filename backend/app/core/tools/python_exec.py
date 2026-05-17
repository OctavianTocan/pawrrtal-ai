"""In-process Python execution as an agent tool.

Exposes a single tool, ``python``, that runs Python source supplied by
the model with :func:`exec` in the FastAPI worker process.  The
execution is *not* sandboxed: code has full access to the import
system, ``os``, ``subprocess``, the network, and every Python object
reachable from the worker.  This is the intentional trade — Pawrrtal
is a single-tenant, self-hosted agent run by the operator on their
own infrastructure, and treating ``python`` as a peer of ``bash`` in
Claude Code keeps the model's capability ceiling honest.

What the tool *does* provide:

  * **Output capture.** ``print()`` and uncaught tracebacks land in a
    string returned to the model.  Captures stdout + stderr
    interleaved, capped via head + tail truncation so tracebacks
    survive.
  * **Wall-clock timeout.** :func:`asyncio.wait_for` cancels the
    awaiter after ``timeout_seconds``.  The worker thread continues
    until it returns; runaway code burns one CPU until the next yield
    point.  Promote to a subprocess executor when that becomes a
    problem in production.
  * **Workspace filesystem.** A ``fs`` global rooted at the user's
    workspace.  Mirrors the semantics of ``read_file`` /
    ``write_file`` / ``list_dir`` (path traversal blocked, UTF-8
    default, ``_resolve_safe`` for containment).
  * **Process-state isolation.** ``sys.path``, ``os.environ``,
    ``warnings.filters``, and the ``logging`` root config are
    snapshotted at call start and restored in ``finally`` so one
    call cannot corrupt the next.  Isolation is *between* calls, not
    *during* — concurrent calls are serialised via an asyncio lock.

What the tool does *not* provide:

  * Sandboxing.  Code can read ``os.environ`` (incl. secrets), call
    ``subprocess.run``, ``socket.socket``, ``sys.exit``.  The
    operator deploys this knowingly.
  * Cross-call state.  Globals are reset every call; persist via
    ``fs.write``.
  * Hard kill on runaway.  See "wall-clock timeout" above.

Composition: gated by ``settings.virtual_python_enabled`` (default
``False``).  Wired in :func:`app.core.agent_tools.build_agent_tools`
between ``markitdown_convert`` and ``send_message``.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import io
import logging
import os
import sys
import traceback
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anyio

from app.core.agent_loop.types import AgentTool
from app.core.tools.errors import ToolError, ToolErrorCode
from app.core.tools.workspace_files import _resolve_safe

log = logging.getLogger(__name__)

# Half of the cap is shown from the head and half from the tail when
# truncating; tracebacks live at the tail and must survive.
_TRUNCATION_MARKER = "[truncated — output exceeded {cap} bytes]"
# Length cap on the ``code`` argument logged at INFO so spammy code
# blobs don't blow up the log stream.
_MAX_LOGGED_CODE_LEN = 500
# Default mode for files created via ``WorkspaceFS.write`` /
# ``write_bytes`` / ``append``.  Same as ``open(..., 'w')`` default
# under a 0o022 umask.
_WRITE_FILE_MODE = 0o644

# Module-level lock so concurrent ``python`` tool calls from
# different requests share one serialisation point.  ``redirect_stdout``
# and the process-state snapshot in ``_isolate_process_state`` are
# process-global, not contextvar-safe — a per-instance lock would let
# two requests on the same worker race on stdout capture and
# ``os.environ`` snapshot/restore.
_EXEC_LOCK = asyncio.Lock()


def _open_workspace_file(target: Path, flags: int, mode: int = 0) -> int:
    """``os.open`` *target* with ``O_NOFOLLOW`` added to *flags*.

    Maps the kernel's ``ELOOP`` (symlink encountered with
    ``O_NOFOLLOW`` set) to a ``PermissionError`` shaped like the
    workspace's ``OUT_OF_ROOT`` rejection so the model sees the same
    error shape whether it tries via the tool or via ``fs``.
    """
    try:
        return os.open(target, flags | os.O_NOFOLLOW, mode)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PermissionError(
                f"'{target}' is a symlink and cannot be opened for safety."
            ) from exc
        raise


# ---------------------------------------------------------------------------
# Workspace filesystem helper (the ``fs`` global exposed to user code)
# ---------------------------------------------------------------------------


class WorkspaceFS:
    """Workspace-rooted filesystem helper exposed inside ``python``.

    All paths are relative to the workspace root; absolute paths are
    accepted but rejected if they escape the root.  Mirrors the
    semantics of the existing ``read_file`` / ``write_file`` /
    ``list_dir`` agent tools so the model sees one consistent FS
    model whether it reaches via tool calls or via this helper.

    Methods raise standard Python exceptions (``FileNotFoundError``,
    ``IsADirectoryError``, ``PermissionError``) instead of returning
    sentinel values: the model already knows how to ``try/except``,
    and a raised exception with a useful message is easier to debug
    from a traceback than a silent ``None`` propagating through code.
    Containment violations raise :class:`PermissionError` with an
    ``OUT_OF_ROOT``-shaped message so the model can recognise them.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _resolve(self, rel_path: str) -> Path:
        """Wrap :func:`_resolve_safe` and convert ``ToolError`` → ``PermissionError``."""
        try:
            return _resolve_safe(self._root, rel_path)
        except ToolError as exc:
            if exc.code == ToolErrorCode.OUT_OF_ROOT:
                raise PermissionError(exc.render()) from exc
            # ``INVALID_PATH`` shows up for unresolvable paths; ``ValueError``
            # is the closest Pythonic shape for "I couldn't parse this."
            raise ValueError(exc.render()) from exc

    def read(self, path: str, *, encoding: str = "utf-8") -> str:
        """Return the file's text content; raises if the file is missing."""
        target = self._resolve(path)
        fd = _open_workspace_file(target, os.O_RDONLY)
        with os.fdopen(fd, "rb") as fh:
            return fh.read().decode(encoding)

    def read_bytes(self, path: str) -> bytes:
        """Return the file's raw bytes."""
        target = self._resolve(path)
        fd = _open_workspace_file(target, os.O_RDONLY)
        with os.fdopen(fd, "rb") as fh:
            return fh.read()

    def write(self, path: str, content: str, *, encoding: str = "utf-8") -> int:
        """Write text content, overwriting; returns bytes written.

        Parent directories are created automatically — same as
        ``write_file``.  Symlinks at *path* are rejected so a
        prior-turn ``os.symlink`` cannot let this call escape the jail.
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode(encoding)
        fd = _open_workspace_file(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            _WRITE_FILE_MODE,
        )
        with os.fdopen(fd, "wb") as fh:
            return fh.write(encoded)

    def write_bytes(self, path: str, content: bytes) -> int:
        """Write raw bytes, overwriting; returns bytes written.

        Symlinks at *path* are rejected (see :meth:`write`).
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = _open_workspace_file(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            _WRITE_FILE_MODE,
        )
        with os.fdopen(fd, "wb") as fh:
            return fh.write(content)

    def append(self, path: str, content: str, *, encoding: str = "utf-8") -> int:
        """Append text content; returns bytes written this call.

        Symlinks at *path* are rejected (see :meth:`write`).
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode(encoding)
        fd = _open_workspace_file(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            _WRITE_FILE_MODE,
        )
        with os.fdopen(fd, "wb") as fh:
            return fh.write(encoded)

    def exists(self, path: str) -> bool:
        """Return ``True`` when the resolved path exists."""
        try:
            return self._resolve(path).exists()
        except (PermissionError, ValueError):
            return False

    def ls(self, path: str = "") -> list[str]:
        """Return sorted entries in *path*; directories end in ``/``.

        Entries are returned relative to *path* (the model's mental
        model is "what's in this directory"), not relative to the
        workspace root.  Use :meth:`glob` for rooted patterns.
        """
        target = self._resolve(path)
        if not target.is_dir():
            raise NotADirectoryError(f"'{path}' is not a directory.")
        return [
            f"{entry.name}/" if entry.is_dir() else entry.name
            for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        ]

    def glob(self, pattern: str) -> list[str]:
        """Glob *pattern* against the workspace root.

        Returns workspace-relative string paths.  Use ``"**/*.py"`` to
        recurse; ``Path.glob`` semantics apply.  Symlinks are excluded
        from results — ``read`` / ``write`` / ``write_bytes`` /
        ``append`` reject symlinks at syscall time via ``O_NOFOLLOW``,
        so listing them here would only produce paths the model can't
        act on.
        """
        return [
            str(p.relative_to(self._root))
            for p in sorted(self._root.glob(pattern))
            if not p.is_symlink()
        ]

    def mkdir(self, path: str, *, parents: bool = True) -> None:
        """Create a directory; ``parents=True`` mirrors ``mkdir -p``."""
        self._resolve(path).mkdir(parents=parents, exist_ok=True)

    def remove(self, path: str) -> None:
        """Delete a regular file; raises on directories or missing paths."""
        target = self._resolve(path)
        if target.is_dir():
            raise IsADirectoryError(f"'{path}' is a directory; use shutil.rmtree.")
        target.unlink()

    def path(self, path: str) -> Path:
        """Return the resolved, containment-checked :class:`Path`.

        Escape hatch for code that needs a ``Path`` (e.g. passing to a
        library API).  The path is still inside the workspace root.
        """
        return self._resolve(path)


# ---------------------------------------------------------------------------
# Process-state isolation
# ---------------------------------------------------------------------------


@contextmanager
def _isolate_process_state() -> Iterator[None]:
    """Snapshot mutable process state and restore it in ``finally``.

    Five fields are restored: ``sys.path``, ``os.environ``,
    ``warnings.filters``, and the root logger's handlers + level.
    These are the surfaces most likely to leak between agent calls
    in ways that confuse subsequent calls or unrelated FastAPI
    request handlers running on the same worker.  ``sys.modules`` is
    deliberately *not* snapshotted: the leak is benign (imports
    accumulate but stay valid) and a 50 ms dict copy on every call
    isn't worth it.
    """
    snap_path = list(sys.path)
    snap_env = dict(os.environ)
    snap_filters = list(warnings.filters)
    snap_handlers = list(logging.root.handlers)
    snap_level = logging.root.level
    try:
        yield
    finally:
        sys.path[:] = snap_path
        os.environ.clear()
        os.environ.update(snap_env)
        # ``warnings.filters`` is typed as ``Sequence`` in stubs but is
        # a real ``list`` at runtime; slice-assign is the standard
        # restore pattern (see CPython's own ``warnings.catch_warnings``).
        warnings.filters[:] = snap_filters  # type: ignore[index]
        logging.root.handlers[:] = snap_handlers
        logging.root.setLevel(snap_level)


# ---------------------------------------------------------------------------
# Output handling
# ---------------------------------------------------------------------------


def _truncate_combined(text: str, cap_bytes: int) -> str:
    """Head + tail truncation so tracebacks at the tail survive."""
    encoded = text.encode("utf-8")
    if len(encoded) <= cap_bytes:
        return text
    half = cap_bytes // 2
    head = encoded[:half].decode("utf-8", errors="replace")
    tail = encoded[-half:].decode("utf-8", errors="replace")
    marker = _TRUNCATION_MARKER.format(cap=cap_bytes)
    return f"{head}\n{marker}\n{tail}"


def _scrub_nul(text: str) -> str:
    """Replace embedded NULs so Postgres ``text`` columns accept the result.

    The agent loop persists every tool result (see
    ``app/core/agent_loop/loop.py``'s ``ToolResultMessage`` write
    path); NULs in JSON survive transport but Postgres rejects them.
    """
    return text.replace("\x00", r"\x00")


# ---------------------------------------------------------------------------
# Synchronous exec body (runs on an anyio worker thread)
# ---------------------------------------------------------------------------


def _exec_sync(code: str, fs: WorkspaceFS, cap_bytes: int) -> str:
    """Compile + ``exec`` *code* and return captured stdout + stderr."""
    buf = io.StringIO()
    with (
        _isolate_process_state(),
        contextlib.redirect_stdout(buf),
        contextlib.redirect_stderr(buf),
    ):
        globals_ns: dict[str, Any] = {"__name__": "__virtual_python__", "fs": fs}
        try:
            compiled = compile(code, "<python tool>", "exec")
            # ``# noqa: S102`` silences ruff/flake8-bandit; ``# nosec B102``
            # silences the pre-commit bandit hook.  Both flag ``exec()`` —
            # which is the documented entire purpose of this tool (see the
            # module docstring + the ``virtual_python_enabled`` settings gate).
            exec(compiled, globals_ns)  # noqa: S102  # nosec B102
        except SystemExit as exit_exc:
            buf.write(f"\n[SystemExit: {exit_exc.code}]\n")
        except BaseException:
            # Surface every traceback to the model: a controlled
            # ``except BaseException`` is the entire point of an exec
            # sandbox — KeyboardInterrupt, AssertionError, anything the
            # agent triggers must come back as text, not crash the loop.
            buf.write("\n" + traceback.format_exc())
    return _scrub_nul(_truncate_combined(buf.getvalue(), cap_bytes))


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def make_virtual_python_tool(
    *,
    workspace_root: Path,
    timeout_seconds: float,
    output_cap_bytes: int,
) -> AgentTool:
    """Return the ``python`` :class:`AgentTool` bound to *workspace_root*.

    Args:
        workspace_root: The user's workspace directory.  Passed to
            :class:`WorkspaceFS` so the ``fs`` global exposed to user
            code stays jailed via the existing ``_resolve_safe`` helper.
        timeout_seconds: Wall-clock budget per call.  The awaiter is
            cancelled at this point; the worker thread keeps running
            (see module docstring).
        output_cap_bytes: Head + tail truncation cap on captured
            stdout + stderr.
    """
    fs = WorkspaceFS(workspace_root)

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        code = str(kwargs.get("code") or "")
        if not code.strip():
            return ToolError(
                ToolErrorCode.INVALID_PATH,
                "The 'code' argument is required and must be non-empty.",
            ).render()
        log.info(
            "PYTHON_TOOL_START tool_call_id=%s code=%r",
            tool_call_id,
            code[:_MAX_LOGGED_CODE_LEN],
        )
        async with _EXEC_LOCK:
            try:
                result = await asyncio.wait_for(
                    anyio.to_thread.run_sync(
                        _exec_sync,
                        code,
                        fs,
                        output_cap_bytes,
                        abandon_on_cancel=True,
                    ),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                log.warning(
                    "PYTHON_TOOL_TIMEOUT tool_call_id=%s timeout_s=%.1f",
                    tool_call_id,
                    timeout_seconds,
                )
                return (
                    f"[timeout] code exceeded {timeout_seconds:.0f}s and was cancelled. "
                    "The Python worker keeps running until it yields; runaway loops hold one CPU."
                )
        log.info(
            "PYTHON_TOOL_END tool_call_id=%s output_bytes=%d",
            tool_call_id,
            len(result),
        )
        return result

    return AgentTool(
        name="python",
        description=(
            "Execute Python code in-process and return captured stdout, stderr, "
            "and any uncaught traceback as a single string. "
            "Globals: `fs` (workspace filesystem helper: `fs.read(path)`, "
            "`fs.write(path, content)`, `fs.ls(path)`, `fs.glob(pattern)`, "
            "`fs.exists(path)`, `fs.path(path)`). "
            "Standard library is fully importable. "
            "State does not persist between calls — save data to the workspace "
            "via `fs.write` if you need it next turn. "
            "Output is head/tail truncated past 32 KB. Wall-clock timeout 30 s. "
            "Use `print(...)` for output (`os.write` and direct fd writes bypass capture)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python source to execute. Multi-line is fine. "
                        "The last expression's value is NOT auto-printed — use "
                        "`print()` explicitly. Soft-limit ~8000 characters; for "
                        "longer programs, write to the workspace first via "
                        "`fs.write` and `import` it."
                    ),
                },
            },
            "required": ["code"],
        },
        execute=execute,
    )
