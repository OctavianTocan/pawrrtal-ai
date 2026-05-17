"""Thin async wrapper around the official Notion CLI (``ntn``).

Every Notion tool in this plugin shells out to ``ntn`` through
:func:`call_ntn`.  The wrapper is deliberately narrow: it injects the
workspace-scoped ``NOTION_API_TOKEN`` and an isolated ``HOME`` for
each call, so two requests from different workspaces never share state
on disk.  ``HOME`` isolation is defence-in-depth — ``ntn login``
should never run server-side, but if it does, the artifacts land in a
throw-away tempdir.

The binary itself is installed into the backend image (``chore(docker):
install ntn`` commit).  In local development, the install instructions
in ``docs/handbook/integrations/notion.md`` get the dev environment
set up.

JSON parsing is opt-in: most ``ntn api`` calls return JSON, but ``ntn
pages get`` returns Markdown.  :func:`call_ntn_json` and
:func:`call_ntn_text` make the caller's intent explicit at the call
site so we don't silently corrupt one with the other's parser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Hard cap on how long any single ``ntn`` call may take.  Notion's
# server-side limits are far below this; we use the timeout primarily to
# bound the impact of a hung subprocess.
NTN_CALL_TIMEOUT_SECONDS = 30.0

# Default binary name. Overridable via the ``NTN_BINARY`` env var so
# Dockerfiles or tests can swap in a pinned path / fake script without
# patching Python imports.
NTN_BINARY_ENV_VAR = "NTN_BINARY"
DEFAULT_NTN_BINARY = "ntn"


class NtnError(RuntimeError):
    """Raised when ``ntn`` exits non-zero.

    Carries the original return code and stderr so callers (typically
    :func:`app.integrations.notion.audit.with_audit`) can record the
    failure mode for ``notion_logs_read`` to surface later.
    """

    def __init__(self, returncode: int, stderr: str) -> None:
        super().__init__(f"ntn exited {returncode}: {stderr.strip()[:300]}")
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class NtnResult:
    """Stdout/stderr pair from a successful ``ntn`` call.

    Kept as bytes so callers can decide between ``.decode()`` text and
    ``json.loads(stdout)`` without us guessing wrong at the seam.
    """

    stdout: bytes
    stderr: bytes


def _resolve_binary() -> str:
    """Return the ``ntn`` binary to exec.

    Honours the ``NTN_BINARY`` env var so the Dockerfile can pin an
    absolute path and tests can point at a deterministic stub.
    """
    return os.environ.get(NTN_BINARY_ENV_VAR, DEFAULT_NTN_BINARY)


def _build_env(token: str, home_dir: str) -> dict[str, str]:
    """Compose the minimal env handed to the subprocess.

    Keeps ``PATH`` so the OS can find shared libraries, but otherwise
    runs with a near-empty environment to limit accidental leakage.
    """
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": home_dir,
        "NOTION_API_TOKEN": token,
        # Disables interactive colour codes that would otherwise pollute
        # the captured stdout when ``ntn`` thinks it's running in a TTY.
        "NO_COLOR": "1",
    }
    # Carry through proxy / locale knobs an operator might have set;
    # everything else is intentionally dropped.
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


async def call_ntn(
    args: Sequence[str],
    *,
    token: str,
    stdin: bytes | None = None,
    timeout_seconds: float = NTN_CALL_TIMEOUT_SECONDS,
) -> NtnResult:
    """Run ``ntn <args>`` and return its raw output.

    Args:
        args: Argument list passed to the binary, *excluding* the program
            name itself (e.g. ``["api", "v1/search", "query=foo"]``).
        token: The workspace's ``NOTION_API_KEY``.  Injected as the
            ``NOTION_API_TOKEN`` env var so ``ntn`` picks it up the same
            way a human shell would.
        stdin: Optional bytes piped to ``ntn``'s stdin.  Used by file
            uploads (``ntn files create``).
        timeout_seconds: Wall-clock budget.  Defaults to
            :data:`NTN_CALL_TIMEOUT_SECONDS`.

    Returns:
        An :class:`NtnResult` with the captured stdout/stderr bytes.

    Raises:
        NtnError: Process exited non-zero.
        asyncio.TimeoutError: Process hit ``timeout_seconds``.  The
            caller's audit-log wrapper translates this to a recorded
            error row, so we don't try to swallow it here.
    """
    binary = _resolve_binary()
    # Use a per-call ephemeral HOME — see module docstring.  The
    # ``with`` block guarantees the directory is removed even when the
    # subprocess raises mid-flight.
    with tempfile.TemporaryDirectory(prefix="pawrrtal-ntn-home-") as home_dir:
        env = _build_env(token, home_dir)
        proc = await asyncio.create_subprocess_exec(
            binary,
            *args,
            env=env,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode != 0:
            raise NtnError(proc.returncode or -1, stderr.decode(errors="replace"))
        return NtnResult(stdout=stdout, stderr=stderr)


async def call_ntn_json(args: Sequence[str], *, token: str, stdin: bytes | None = None) -> Any:
    """Run an ``ntn`` command that emits JSON; return the parsed body."""
    result = await call_ntn(args, token=token, stdin=stdin)
    if not result.stdout:
        return None
    return json.loads(result.stdout)


async def call_ntn_text(args: Sequence[str], *, token: str, stdin: bytes | None = None) -> str:
    """Run an ``ntn`` command that emits Markdown / plain text."""
    result = await call_ntn(args, token=token, stdin=stdin)
    return result.stdout.decode(errors="replace")


def format_query_params(params: Mapping[str, str]) -> list[str]:
    """Translate a ``{key: value}`` map into ``key==value`` arg tokens.

    ``ntn api`` uses ``==`` for query-string params and ``=`` for body
    fields (per its built-in help text).  Callers should pass body
    fields directly as ``"foo=bar"`` strings; this helper exists for
    the query-string case so we don't sprinkle ``==`` literals across
    eighteen tool factories.
    """
    return [f"{key}=={value}" for key, value in params.items() if value != ""]
