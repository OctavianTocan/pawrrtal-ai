"""Bounded wrapper around the official Notion CLI (``ntn``).

The Notion plugin shells out to ``ntn`` through :func:`call_ntn`.  The
wrapper is deliberately narrow: it injects the workspace-scoped
``NOTION_API_TOKEN`` and an isolated ``HOME`` for each call, so two
requests from different workspaces never share state on disk.
``HOME`` isolation is defence-in-depth — ``ntn login`` should never
run server-side, but if it does, the artifacts land in a throw-away
tempdir.

The binary itself is installed into the backend image (see the
``ntn``-related comments in ``backend/Dockerfile``).  In local
development, the install instructions in
``docs/handbook/integrations/notion.md`` get the dev environment set
up.
"""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404 - required for the fixed-binary ntn wrapper; no shell is used.
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass

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
    failure mode against ``notion_operation_logs`` for later analysis.
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


def _run_ntn_sync(
    *,
    binary: str,
    args: Sequence[str],
    env: dict[str, str],
    stdin: bytes | None,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    """Run the blocking subprocess call.

    Python 3.13 async subprocesses and thread handoff both hang in the
    local sandbox, while direct ``subprocess.run`` remains bounded and
    kills the child process on timeout.
    """
    return subprocess.run(  # noqa: S603  # nosec B603 - fixed binary + argv list, no shell.
        [binary, *args],
        input=stdin,
        env=env,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


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
        TimeoutError: Process hit ``timeout_seconds``.  The caller's
            audit-log wrapper translates this to a recorded error row,
            so we don't try to swallow it here.
    """
    binary = _resolve_binary()
    # Use a per-call ephemeral HOME — see module docstring.  The
    # ``with`` block guarantees the directory is removed even when the
    # subprocess raises mid-flight.
    with tempfile.TemporaryDirectory(prefix="pawrrtal-ntn-home-") as home_dir:
        env = _build_env(token, home_dir)
        try:
            completed = _run_ntn_sync(
                binary=binary,
                args=args,
                env=env,
                stdin=stdin,
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"ntn timed out after {timeout_seconds:.1f}s") from exc
        if completed.returncode != 0:
            raise NtnError(
                completed.returncode or -1,
                completed.stderr.decode(errors="replace"),
            )
        return NtnResult(stdout=completed.stdout, stderr=completed.stderr)
