"""Hardened subprocess runner for CLI plugin capabilities."""

from __future__ import annotations

import os
import signal
import subprocess  # nosec B404 - plugin CLI execution intentionally uses subprocess.
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anyio

from app.plugins.errors import PluginRuntimeError

BASE_ENV_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LD_LIBRARY_PATH",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
)
DEFAULT_OUTPUT_CAP_BYTES = 32_000


@dataclass(frozen=True, slots=True)
class CliRunRequest:
    """Inputs for one CLI plugin subprocess run."""

    argv: tuple[str, ...]
    plugin_dir: Path
    workspace_root: Path
    cwd_mode: str
    env: dict[str, str]
    stdin: str | None = None
    timeout_seconds: int = 30
    output_cap_bytes: int = DEFAULT_OUTPUT_CAP_BYTES


@dataclass(frozen=True, slots=True)
class CliRunResult:
    """Stable result envelope for one CLI plugin subprocess run."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def success(self) -> bool:
        """Return whether the subprocess completed successfully."""
        return self.returncode == 0 and not self.timed_out

    def to_data(self) -> dict[str, object]:
        """Return JSON-serializable process data."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
        }


async def run_cli_plugin(request: CliRunRequest) -> CliRunResult:
    """Run a plugin subprocess off-thread and return a bounded result."""
    return await anyio.to_thread.run_sync(_run_cli_plugin_sync, request)


def _run_cli_plugin_sync(request: CliRunRequest) -> CliRunResult:
    """Run a plugin subprocess synchronously with containment checks."""
    argv = _validate_argv(request.argv, request.plugin_dir, request.workspace_root)
    cwd = _resolve_cwd(request)
    stdin_bytes = request.stdin.encode("utf-8") if request.stdin is not None else None
    with tempfile.TemporaryDirectory(prefix="paw-plugin-home-") as home_dir:
        env = _build_env(request.env, home_dir)
        process = subprocess.Popen(  # noqa: S603  # nosec B603 - argv list, shell=False.
            list(argv),
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE if stdin_bytes is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(
                input=stdin_bytes,
                timeout=request.timeout_seconds,
            )
            return _completed_result(
                stdout=stdout,
                stderr=stderr,
                returncode=process.returncode,
                output_cap_bytes=request.output_cap_bytes,
            )
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            stdout, stderr = process.communicate()
            return _completed_result(
                stdout=stdout,
                stderr=stderr,
                returncode=process.returncode or -signal.SIGTERM,
                output_cap_bytes=request.output_cap_bytes,
                timed_out=True,
            )


def _validate_argv(
    argv: tuple[str, ...],
    plugin_dir: Path,
    workspace_root: Path,
) -> tuple[str, ...]:
    """Validate argv and reject unsafe local entrypoints."""
    if not argv:
        raise PluginRuntimeError("CLI plugin argv must not be empty.")
    first = argv[0]
    if not first.strip():
        raise PluginRuntimeError("CLI plugin argv[0] must not be empty.")
    if first.startswith("./") or "/" in first:
        _validate_local_entrypoint(first, plugin_dir, workspace_root)
    return argv


def _validate_local_entrypoint(first: str, plugin_dir: Path, workspace_root: Path) -> None:
    """Reject symlinked or out-of-root local entrypoints."""
    raw = (plugin_dir / first) if first.startswith("./") else Path(first)
    if raw.is_symlink():
        raise PluginRuntimeError(f"CLI entrypoint must not be a symlink: {first}")
    resolved = raw.resolve()
    plugin_root = plugin_dir.resolve()
    workspace = workspace_root.resolve()
    if _is_inside(resolved, plugin_root) or _is_inside(resolved, workspace):
        return
    raise PluginRuntimeError(f"CLI entrypoint escapes plugin/workspace roots: {first}")


def _resolve_cwd(request: CliRunRequest) -> Path:
    """Resolve and validate the subprocess cwd."""
    if request.cwd_mode == "plugin":
        cwd = request.plugin_dir.resolve()
        root = request.plugin_dir.resolve()
    elif request.cwd_mode == "workspace":
        cwd = request.workspace_root.resolve()
        root = request.workspace_root.resolve()
    else:
        raise PluginRuntimeError(f"Unknown CLI cwd mode: {request.cwd_mode}")
    if not _is_inside(cwd, root):
        raise PluginRuntimeError("CLI cwd escapes its allowed root.")
    return cwd


def _build_env(plugin_env: dict[str, str], home_dir: str) -> dict[str, str]:
    """Build a scrubbed subprocess environment."""
    env = {key: value for key in BASE_ENV_KEYS if (value := os.environ.get(key))}
    env["HOME"] = home_dir
    env["NO_COLOR"] = "1"
    env.update(plugin_env)
    return env


def _completed_result(
    *,
    stdout: bytes,
    stderr: bytes,
    returncode: int,
    output_cap_bytes: int,
    timed_out: bool = False,
) -> CliRunResult:
    """Decode and cap subprocess output streams."""
    capped_stdout, stdout_truncated = _cap_bytes(stdout, output_cap_bytes)
    capped_stderr, stderr_truncated = _cap_bytes(stderr, output_cap_bytes)
    return CliRunResult(
        stdout=capped_stdout.decode("utf-8", errors="replace"),
        stderr=capped_stderr.decode("utf-8", errors="replace"),
        returncode=returncode,
        timed_out=timed_out,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def _cap_bytes(data: bytes, cap: int) -> tuple[bytes, bool]:
    """Return data capped to ``cap`` bytes plus truncation state."""
    if len(data) <= cap:
        return data, False
    return data[:cap], True


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate a subprocess group created with ``start_new_session``."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _is_inside(path: Path, root: Path) -> bool:
    """Return whether ``path`` is equal to or below ``root``."""
    return path == root or path.is_relative_to(root)
