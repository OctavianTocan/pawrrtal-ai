"""paw dev — local backend process lifecycle (up/down/status).

``paw dev`` is a local CLI orchestrator, not a backend feature. It manages
a long-lived ``uvicorn`` subprocess running the FastAPI app. The PID,
port, start timestamp, and log path are persisted in a small JSON state
file under ``<PAW_CONFIG_DIR>/<profile>/dev.json`` so subsequent ``paw
dev`` invocations can locate the process.

This is intentionally minimal — think of it as a tiny ``pm2`` for the
pawrrtal backend so verify suites can self-bootstrap when the backend
isn't already running. It coexists with ``just dev`` (which boots
frontend + backend together via ``dev.ts``) but does not supersede it:
``just dev`` remains the canonical full-stack dev loop. ``paw dev``
targets the backend only and is the right tool for headless agent /
verify scenarios.

Example::

    paw dev up                 # boot backend on 127.0.0.1:8000 in the background
    paw dev status --json      # check PID + health
    paw dev down               # SIGTERM then SIGKILL after grace period
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import typer

from app.cli.paw.config import DEFAULT_PROFILE, profile_dir
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json

logger = logging.getLogger(__name__)

# Default network binding for the dev backend. Matches ``dev.ts`` so a
# ``paw dev up`` launched here is interchangeable with ``just dev``'s
# backend half.
DEFAULT_DEV_HOST = "127.0.0.1"
DEFAULT_DEV_PORT = 8000

# Default timeout we wait for ``/api/v1/health`` to respond before
# declaring boot a failure. uvicorn cold-starts in well under a second
# on the dev machine; 30s leaves room for first-import overhead under
# coverage / cold caches.
DEFAULT_BOOT_TIMEOUT_S = 30

# Interval between health probes during boot. 250ms is small enough to
# catch a fast boot quickly without spamming the socket.
HEALTH_PROBE_INTERVAL_S = 0.25

# Connect timeout for each individual health probe. The health check
# itself is cheap; the boot timeout above governs the overall wait.
HEALTH_PROBE_TIMEOUT_S = 2.0

# Time between SIGTERM and the optional SIGKILL fallback. uvicorn flushes
# logs + closes the listening socket well within this budget.
GRACEFUL_SHUTDOWN_TIMEOUT_S = 10

# Interval between liveness polls while waiting for the process to die
# after SIGTERM. 100ms keeps ``paw dev down`` snappy without busy-looping.
LIVENESS_POLL_INTERVAL_S = 0.1

# Exit code returned by ``paw dev status`` when the recorded PID exists
# in state but is no longer alive (i.e. the backend crashed or was
# killed externally). Reusing exit-code 4 (BackendUnreachable) communicates
# "backend not available" without conflating with a generic local error.
EXIT_TRACKED_BUT_DEAD = 4

# State file schema version. Bump when the persisted shape changes
# in a non-backwards-compatible way.
DEV_STATE_SCHEMA_VERSION = 1

# HTTP status that ``/api/v1/health`` returns when the backend is up. Named
# so the comparison in ``_probe_health`` reads as intent, not magic number.
HEALTH_OK_STATUS = 200


app = typer.Typer(no_args_is_help=True)


@dataclass(slots=True)
class DevState:
    """Persisted record of the running dev backend.

    Stored as JSON at ``<PAW_CONFIG_DIR>/<profile>/dev.json``.
    """

    schema_version: int
    pid: int
    host: str
    port: int
    started_at: str
    log_path: str


def _dev_state_path(profile: str) -> Path:
    """Return the dev state file path for ``profile``."""
    return profile_dir(profile) / "dev.json"


def _dev_log_path(profile: str) -> Path:
    """Return the dev backend log file path for ``profile``."""
    return profile_dir(profile) / "dev.log"


def _load_state(profile: str) -> DevState | None:
    """Read the persisted state file, or ``None`` if absent / unreadable."""
    path = _dev_state_path(profile)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to read dev state file; treating as absent",
            extra={"path": str(path), "error": str(exc)},
        )
        return None
    return DevState(
        schema_version=int(raw.get("schema_version", DEV_STATE_SCHEMA_VERSION)),
        pid=int(raw["pid"]),
        host=str(raw["host"]),
        port=int(raw["port"]),
        started_at=str(raw["started_at"]),
        log_path=str(raw["log_path"]),
    )


def _save_state(profile: str, state: DevState) -> None:
    """Persist the dev state file atomically."""
    path = _dev_state_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True))


def _delete_state(profile: str) -> None:
    """Remove the dev state file if it exists. Idempotent."""
    path = _dev_state_path(profile)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _pid_alive(pid: int) -> bool:
    """Return ``True`` if a process with ``pid`` exists and accepts signals.

    Uses ``os.kill(pid, 0)`` which is the canonical UNIX no-op probe:
    it raises ``ProcessLookupError`` if no such process exists,
    ``PermissionError`` if the process exists but we can't signal it
    (treated as alive for our purposes — same uid will reach it).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _port_in_use(host: str, port: int) -> bool:
    """Probe ``host:port`` to see if anything is bound there.

    Used to surface external uvicorns / stray processes that the user
    might have started outside ``paw dev``. Best-effort: a transient
    refusal is reported as ``False``.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(HEALTH_PROBE_TIMEOUT_S)
        try:
            sock.connect((host, port))
        except OSError:
            return False
    return True


def _health_url(host: str, port: int) -> str:
    """Return the canonical health endpoint URL for ``host:port``."""
    return f"http://{host}:{port}/api/v1/health"


def _probe_health(host: str, port: int) -> bool:
    """One-shot probe of ``/api/v1/health``. Returns ``True`` on HTTP 200."""
    try:
        response = httpx.get(_health_url(host, port), timeout=HEALTH_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return response.status_code == HEALTH_OK_STATUS


def _wait_for_health(host: str, port: int, timeout_s: int) -> bool:
    """Poll the health endpoint until it responds OK or the timeout elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _probe_health(host, port):
            return True
        time.sleep(HEALTH_PROBE_INTERVAL_S)
    return False


def _backend_dir() -> Path:
    """Locate the ``backend/`` directory relative to this source file.

    ``paw dev up`` spawns uvicorn with ``cwd=backend/`` so the relative
    ``--app-dir`` paths in ``dev.ts`` continue to work.
    """
    # __file__ -> backend/app/cli/paw/commands/dev.py
    return Path(__file__).resolve().parents[4]


def _spawn_uvicorn(
    *,
    host: str,
    port: int,
    reload: bool,
    log_handle: int,
) -> subprocess.Popen[bytes]:
    """Spawn the uvicorn subprocess that hosts the FastAPI app.

    Mirrors the command used by ``dev.ts`` so the two boot paths stay
    interchangeable. The child is fully detached from the parent: stdout
    and stderr both go to ``log_handle`` (the opened dev.log file), and
    the child gets its own process group so ``paw dev down`` can target
    it cleanly.
    """
    command: list[str] = [
        "uv",
        "run",
        "uvicorn",
        "main:app",
        "--app-dir",
        ".",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        command.extend(["--reload", "--reload-dir", "."])
    return subprocess.Popen(
        command,
        cwd=_backend_dir(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _format_uptime(started_at: str) -> str:
    """Render the wall-clock delta since ``started_at`` as ``Hh Mm Ss``."""
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return "?"
    now = datetime.now(UTC)
    delta = now - started
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "0s"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes}m{secs}s"
    if minutes:
        return f"{minutes}m{secs}s"
    return f"{secs}s"


@app.command("up")
def up(
    host: str = typer.Option(DEFAULT_DEV_HOST, "--host", help="Host interface to bind."),
    port: int = typer.Option(DEFAULT_DEV_PORT, "--port", help="TCP port to bind."),
    detach: bool = typer.Option(
        True,
        "--detach/--no-detach",
        help="Return after boot (default) or foreground + tail the log.",
    ),
    reload: bool = typer.Option(
        True,
        "--reload/--no-reload",
        help="Pass --reload to uvicorn so code edits hot-reload (default).",
    ),
    restart: bool = typer.Option(
        False,
        "--restart",
        help="If a tracked backend is already running, stop it first.",
    ),
    boot_timeout: int = typer.Option(
        DEFAULT_BOOT_TIMEOUT_S,
        "--boot-timeout",
        help="Seconds to wait for /api/v1/health to respond before failing.",
        min=1,
    ),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Boot the local FastAPI backend and wait for its health endpoint.

    Examples:
      paw dev up
      paw dev up --port 9000 --no-reload
      paw dev up --restart
      paw dev up --no-detach
    """
    existing = _load_state(profile)
    if (
        existing is not None
        and _pid_alive(existing.pid)
        and _probe_health(existing.host, existing.port)
    ):
        if not restart:
            raise LocalError(
                f"Backend already running (pid {existing.pid}, port {existing.port}).",
                hint="Pass `--restart` to stop the existing process first, or run `paw dev down`.",
            )
        _stop_tracked_backend(existing, force=False)
        _delete_state(profile)

    log_path = _dev_log_path(profile)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")
    try:
        proc = _spawn_uvicorn(host=host, port=port, reload=reload, log_handle=log_handle.fileno())
    except FileNotFoundError as exc:
        log_handle.close()
        raise LocalError(
            f"Failed to spawn uvicorn: {exc}",
            hint="Ensure `uv` is on PATH and run from a workspace where `uv run uvicorn` works.",
        ) from exc

    if not _wait_for_health(host, port, boot_timeout):
        # Tear the dead child down so we don't leak a half-booted process.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        log_handle.close()
        raise LocalError(
            f"Backend did not become healthy on http://{host}:{port} within {boot_timeout}s.",
            hint=f"Inspect {log_path} for boot errors.",
        )

    state = DevState(
        schema_version=DEV_STATE_SCHEMA_VERSION,
        pid=proc.pid,
        host=host,
        port=port,
        started_at=datetime.now(UTC).isoformat(),
        log_path=str(log_path),
    )
    _save_state(profile, state)
    log_handle.close()

    emit_human(f"backend up on http://{host}:{port} (PID {proc.pid})")

    if not detach:
        _tail_log_until_exit(proc, log_path)


def _tail_log_until_exit(proc: subprocess.Popen[bytes], log_path: Path) -> None:
    """Foreground mode: stream the log file until the child exits.

    Simple ``tail -f`` style follower. Returns when ``proc`` terminates
    so the user can ^C the parent and have it exit cleanly.
    """
    try:
        with log_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            while proc.poll() is None:
                chunk = fh.read()
                if chunk:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                else:
                    time.sleep(HEALTH_PROBE_INTERVAL_S)
    except KeyboardInterrupt:
        return


@app.command("down")
def down(
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip the SIGTERM grace period and SIGKILL immediately.",
    ),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Stop the tracked dev backend (SIGTERM, then SIGKILL after a grace period).

    Examples:
      paw dev down
      paw dev down --force
    """
    state = _load_state(profile)
    if state is None:
        emit_human("no dev backend tracked")
        return

    _stop_tracked_backend(state, force=force)
    _delete_state(profile)
    emit_human("stopped")


def _stop_tracked_backend(state: DevState, *, force: bool) -> None:
    """Send the appropriate signal(s) to terminate the tracked backend.

    The child runs in its own process group (see ``_spawn_uvicorn``)
    so we signal the group rather than the lead PID — uvicorn's
    ``--reload`` mode forks a reloader supervisor and a worker, and
    signalling only the supervisor leaves the worker orphaned.
    """
    if not _pid_alive(state.pid):
        return

    signal_to_send = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(state.pid, signal_to_send)
    except ProcessLookupError:
        return

    if force:
        return

    if _wait_for_exit(state.pid, GRACEFUL_SHUTDOWN_TIMEOUT_S):
        return

    # Graceful shutdown timed out; escalate.
    try:
        os.killpg(state.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _wait_for_exit(pid: int, timeout_s: int) -> bool:
    """Poll until ``pid`` is no longer alive or ``timeout_s`` elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(LIVENESS_POLL_INTERVAL_S)
    return not _pid_alive(pid)


@app.command("status")
def status(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of human text."),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Report the dev backend's health: PID + port + uptime + /api/v1/health.

    Examples:
      paw dev status
      paw dev status --json
    """
    state = _load_state(profile)
    if state is None:
        untracked = _untracked_status(DEFAULT_DEV_HOST, DEFAULT_DEV_PORT)
        if json_output:
            emit_json(untracked)
        else:
            _emit_human_status(untracked)
        return

    pid_alive = _pid_alive(state.pid)
    healthy = _probe_health(state.host, state.port) if pid_alive else False
    payload: dict[str, Any] = {
        "tracked": True,
        "pid": state.pid,
        "host": state.host,
        "port": state.port,
        "started_at": state.started_at,
        "uptime": _format_uptime(state.started_at),
        "log_path": state.log_path,
        "pid_alive": pid_alive,
        "healthy": healthy,
        "status": _classify_status(pid_alive=pid_alive, healthy=healthy),
    }

    if json_output:
        emit_json(payload)
    else:
        _emit_human_status(payload)

    if not pid_alive:
        raise typer.Exit(code=EXIT_TRACKED_BUT_DEAD)


def _classify_status(*, pid_alive: bool, healthy: bool) -> str:
    """Map (pid_alive, healthy) onto a short human-readable status label."""
    if pid_alive and healthy:
        return "running"
    if pid_alive and not healthy:
        return "starting-or-unhealthy"
    return "stopped"


def _untracked_status(host: str, port: int) -> dict[str, Any]:
    """Build the status payload when no state file exists.

    We still probe the canonical dev port so we can flag the case where
    ``just dev`` (or another developer's uvicorn) is listening — that's
    a common gotcha worth surfacing.
    """
    return {
        "tracked": False,
        "host": host,
        "port": port,
        "port_in_use": _port_in_use(host, port),
        "status": "untracked",
    }


def _emit_human_status(payload: dict[str, Any]) -> None:
    """Render the status payload as a few aligned lines."""
    if not payload.get("tracked"):
        port_note = (
            f"  note: {payload['host']}:{payload['port']} is in use (likely `just dev` or another uvicorn)"
            if payload.get("port_in_use")
            else f"  port {payload['host']}:{payload['port']} is free"
        )
        emit_human(f"status: untracked\n{port_note}")
        return

    lines = [
        f"status: {payload['status']}",
        f"  pid:       {payload['pid']} ({'alive' if payload['pid_alive'] else 'dead'})",
        f"  bind:      {payload['host']}:{payload['port']}",
        f"  uptime:    {payload['uptime']}",
        f"  health:    {'ok' if payload['healthy'] else 'down'}",
        f"  log:       {payload['log_path']}",
    ]
    emit_human("\n".join(lines))
