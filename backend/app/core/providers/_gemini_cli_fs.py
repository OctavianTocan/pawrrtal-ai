"""Filesystem callbacks for the Gemini CLI ACP client.

Split out of :mod:`_gemini_cli_client` to keep that module under the
500-line gate. Pure helpers — no ACP class, no event-queue coupling.
Owns the workspace-path safety check and the OS-error-to-``RequestError``
translation used by ``fs/read_text_file`` / ``fs/write_text_file``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from acp import RequestError

logger = logging.getLogger(__name__)


FS_READ_BYTES_LIMIT = 1024 * 1024
"""Hard cap on a single ``fs/read_text_file`` payload. Protects the
gateway from a misbehaving agent asking to slurp a multi-gigabyte
file into memory — the spec's optional ``line`` / ``limit`` only
slice *after* the full read."""


def ensure_workspace_path(path: str, workspace_root: Path | None) -> Path:
    """Validate ``path`` is absolute and resolved under ``workspace_root``.

    Defence-in-depth: the ACP spec already requires absolute paths on
    ``fs/*`` methods, but a buggy agent sending a relative path would
    otherwise be resolved against :func:`Path.cwd` and escape the
    workspace via traversal. ``Path.resolve()`` follows symlinks before
    the containment check, so a symlink inside the workspace pointing
    at a host file is also rejected.

    Raises :exc:`acp.RequestError.invalid_params` on every rejection so
    the agent self-corrects on the next turn.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        raise RequestError.invalid_params(
            {"path": path, "reason": "path must be absolute"},
        )
    if workspace_root is None:
        raise RequestError.invalid_params(
            {"path": path, "reason": "filesystem access not enabled for this session"},
        )
    resolved = candidate.resolve()
    workspace_resolved = workspace_root.resolve()
    if not resolved.is_relative_to(workspace_resolved):
        raise RequestError.invalid_params(
            {"path": path, "reason": "path is outside the workspace"},
        )
    return resolved


def read_text_or_raise(resolved: Path, original_path: str) -> str:
    """Read ``resolved`` as text, converting OS errors to ``RequestError``.

    Enforces :data:`FS_READ_BYTES_LIMIT` before the read so the gateway
    cannot be coerced into loading a huge file into memory.
    """
    try:
        stat_size = resolved.stat().st_size
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise RequestError.invalid_params(
            {"path": original_path, "reason": f"stat failed: {exc}"},
        ) from exc
    if stat_size > FS_READ_BYTES_LIMIT:
        raise RequestError.invalid_params(
            {
                "path": original_path,
                "reason": (
                    f"file is {stat_size} bytes; cap is {FS_READ_BYTES_LIMIT}. "
                    "Use line+limit to slice."
                ),
            },
        )
    try:
        return resolved.read_text()
    except FileNotFoundError as exc:
        raise RequestError.invalid_params(
            {"path": original_path, "reason": "not found"},
        ) from exc
    except PermissionError as exc:
        raise RequestError.invalid_params(
            {"path": original_path, "reason": "permission denied"},
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("GEMINI_CLI_FS_READ_FAILED path=%s reason=%s", original_path, exc)
        raise RequestError.invalid_params(
            {"path": original_path, "reason": str(exc)},
        ) from exc


def write_text_or_raise(resolved: Path, content: str, original_path: str) -> None:
    """Write ``content`` to ``resolved``, converting OS errors to ``RequestError``."""
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
    except PermissionError as exc:
        raise RequestError.invalid_params(
            {"path": original_path, "reason": "permission denied"},
        ) from exc
    except OSError as exc:
        logger.warning("GEMINI_CLI_FS_WRITE_FAILED path=%s reason=%s", original_path, exc)
        raise RequestError.invalid_params(
            {"path": original_path, "reason": str(exc)},
        ) from exc


def slice_text(content: str, line: int | None, limit: int | None) -> str:
    """Return ``content`` sliced by 1-based ``line`` / ``limit`` lines.

    Mirrors the ACP spec's ``fs/read_text_file`` semantics: ``line`` is
    the 1-based starting line, ``limit`` caps the number of returned
    lines. Out-of-range values are clamped so the agent self-corrects
    on the next read instead of erroring.
    """
    lines = content.splitlines()
    start = max((line or 1) - 1, 0)
    end = len(lines)
    if limit is not None:
        end = min(start + limit, end)
    return "\n".join(lines[start:end])
