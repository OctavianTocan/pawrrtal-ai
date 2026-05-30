"""Whole-project dev lifecycle commands for ``paw project``.

``paw dev`` intentionally manages only the FastAPI backend. This module
wraps the root ``dev.ts`` orchestrator so an operator can start, stop,
inspect, and find logs for the full local app from the CLI: Next.js on
``localhost:53001`` and FastAPI on ``127.0.0.1:8000``.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import typer

from app.cli.paw.commands.dev.process import process_create_time
from app.cli.paw.commands.project.preflight import (
    emit_preflight,
    exit_if_preflight_failed,
    raise_if_preflight_failed,
    run_preflight_checks,
)
from app.cli.paw.commands.project.service import app as service_app
from app.cli.paw.commands.project.state import (
    DEFAULT_BACKEND_URL,
    DEFAULT_BOOT_TIMEOUT_S,
    DEFAULT_FRONTEND_URL,
    GRACEFUL_SHUTDOWN_TIMEOUT_S,
    HEALTH_PROBE_INTERVAL_S,
    HEALTH_PROBE_TIMEOUT_S,
    PID_RECYCLE_TOLERANCE_S,
    PROJECT_STATE_SCHEMA_VERSION,
    SERVER_ERROR_STATUS,
    ProjectState,
    delete_state,
    load_state,
    project_log_path,
    project_state_path,
    repo_root,
    save_state,
)
from app.cli.paw.config import DEFAULT_PROFILE
from app.cli.paw.errors import EXIT_DEV_DEAD, LocalError
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

app = typer.Typer(no_args_is_help=True)
env_app = typer.Typer(no_args_is_help=True)
app.add_typer(service_app, name="service", help="Install/manage the user systemd dev service.")


def pid_alive(pid: int) -> bool:
    """Return ``True`` when a process with ``pid`` exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def spawn_project(*, log_handle: int) -> subprocess.Popen[bytes]:
    """Spawn the root ``dev.ts`` orchestrator in its own process group."""
    env = _project_env()
    return subprocess.Popen(
        ["bun", "run", "dev.ts"],
        cwd=repo_root(),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _project_env() -> dict[str, str]:
    """Build the child env, forcing cache writes into the workspace."""
    env = os.environ.copy()
    cache_root = repo_root() / ".cache"
    env.setdefault("UV_CACHE_DIR", str(cache_root / "uv"))
    env.setdefault("XDG_CACHE_HOME", str(cache_root / "xdg"))
    env["DATABASE_URL"] = env.get("PAWRRTAL_DEV_DATABASE_URL", "")
    return env


def _backend_health_url(backend_url: str) -> str:
    """Return the backend health URL for a base backend URL."""
    return f"{backend_url.rstrip('/')}/api/v1/health"


def probe_url(url: str) -> bool:
    """Return ``True`` if ``url`` responds with a non-5xx status."""
    try:
        response = httpx.get(url, timeout=HEALTH_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return response.status_code < SERVER_ERROR_STATUS


def project_healthy(frontend_url: str, backend_url: str) -> tuple[bool, bool]:
    """Probe the frontend and backend surfaces."""
    frontend_ok = probe_url(frontend_url)
    backend_ok = probe_url(_backend_health_url(backend_url))
    return frontend_ok, backend_ok


def wait_for_project(frontend_url: str, backend_url: str, timeout_s: int) -> bool:
    """Wait until both local dev services respond."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if all(project_healthy(frontend_url, backend_url)):
            return True
        time.sleep(HEALTH_PROBE_INTERVAL_S)
    return False


def stop_project_state(state: ProjectState, *, force: bool) -> None:
    """Stop the tracked full-project dev process group."""
    if not pid_alive(state.pid):
        return
    if _pid_recycled(state):
        raise LocalError(
            f"Refusing to signal PID {state.pid}; it may not be the tracked project process.",
            hint=f"Remove stale state manually: {project_state_path(DEFAULT_PROFILE)}",
        )
    sig = signal.SIGKILL if force else signal.SIGTERM
    os.killpg(state.pid, sig)
    if force:
        return
    _wait_for_exit_or_kill(state.pid)


def _pid_recycled(state: ProjectState) -> bool:
    """Return True when the live PID creation time does not match state."""
    if state.start_time is None:
        return False
    live_start = process_create_time(state.pid)
    if live_start is None:
        return False
    return abs(live_start - state.start_time) > PID_RECYCLE_TOLERANCE_S


def _wait_for_exit_or_kill(pid: int) -> None:
    """Wait for graceful shutdown, then SIGKILL if still alive."""
    deadline = time.monotonic() + GRACEFUL_SHUTDOWN_TIMEOUT_S
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return
        time.sleep(0.1)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def _uptime_seconds(started_at: str) -> int:
    """Return integer seconds since ``started_at``."""
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0
    return max(int((datetime.now(UTC) - started).total_seconds()), 0)


def _status_payload(state: ProjectState | None) -> dict[str, Any]:
    """Build a structured status payload."""
    if state is None:
        return {
            "tracked": False,
            "status": "untracked",
            "pid": None,
            "frontend_url": DEFAULT_FRONTEND_URL,
            "backend_url": DEFAULT_BACKEND_URL,
            "frontend_healthy": probe_url(DEFAULT_FRONTEND_URL),
            "backend_healthy": probe_url(_backend_health_url(DEFAULT_BACKEND_URL)),
        }
    alive = pid_alive(state.pid)
    frontend_ok, backend_ok = (
        project_healthy(state.frontend_url, state.backend_url) if alive else (False, False)
    )
    return {
        "tracked": True,
        "status": _classify_status(alive=alive, frontend_ok=frontend_ok, backend_ok=backend_ok),
        "pid": state.pid,
        "started_at": state.started_at,
        "uptime_s": _uptime_seconds(state.started_at),
        "log_path": state.log_path,
        "frontend_url": state.frontend_url,
        "backend_url": state.backend_url,
        "frontend_healthy": frontend_ok,
        "backend_healthy": backend_ok,
    }


def _classify_status(*, alive: bool, frontend_ok: bool, backend_ok: bool) -> str:
    """Map process and service health to a compact status label."""
    if alive and frontend_ok and backend_ok:
        return "running"
    if alive:
        return "starting-or-unhealthy"
    return "stopped"


def _emit_project_payload(payload: dict[str, Any], *, json_out: bool, plain: bool) -> None:
    """Emit project status in the selected output mode."""
    if json_out:
        emit_json(payload)
        return
    if plain:
        emit_plain_rows(
            [
                [
                    payload.get("pid"),
                    payload["status"],
                    "ok" if payload["frontend_healthy"] else "down",
                    "ok" if payload["backend_healthy"] else "down",
                ]
            ]
        )
        return
    emit_human(
        "\n".join(
            [
                f"status: {payload['status']}",
                f"pid: {payload.get('pid') or ''}",
                f"frontend: {payload['frontend_url']} ({'ok' if payload['frontend_healthy'] else 'down'})",
                f"backend: {payload['backend_url']} ({'ok' if payload['backend_healthy'] else 'down'})",
            ]
        )
    )


@app.command("up")
def up(
    restart: bool = typer.Option(
        False, "--restart", help="Stop an existing tracked project first."
    ),
    boot_timeout: int = typer.Option(
        DEFAULT_BOOT_TIMEOUT_S,
        "--boot-timeout",
        help="Seconds to wait for frontend + backend health.",
        min=1,
    ),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Start the full local project: frontend + backend."""
    _start_project(restart=restart, boot_timeout=boot_timeout, profile=profile)


def _start_project(*, restart: bool, boot_timeout: int, profile: str) -> None:
    """Start the full local project with plain Python parameters."""
    checks = run_preflight_checks(profile=profile)
    if restart:
        checks = [
            check
            for check in checks
            if check.name not in {"frontend_port_available", "backend_port_available"}
        ]
    raise_if_preflight_failed(checks)

    existing = load_state(profile)
    if existing is not None and pid_alive(existing.pid):
        if not restart:
            raise LocalError(
                f"Project already running (pid {existing.pid}).",
                hint="Run `paw project down`, or pass `--restart`.",
            )
        stop_project_state(existing, force=False)
        delete_state(profile)

    log_path = project_log_path(profile)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_handle:
        proc = spawn_project(log_handle=log_handle.fileno())
        if not wait_for_project(DEFAULT_FRONTEND_URL, DEFAULT_BACKEND_URL, boot_timeout):
            _terminate_failed_boot(proc)
            raise LocalError(
                f"Project did not become healthy within {boot_timeout}s.",
                hint=f"Inspect {log_path} for startup errors.",
            )
        state = ProjectState(
            schema_version=PROJECT_STATE_SCHEMA_VERSION,
            pid=proc.pid,
            started_at=datetime.now(UTC).isoformat(),
            log_path=str(log_path),
            frontend_url=DEFAULT_FRONTEND_URL,
            backend_url=DEFAULT_BACKEND_URL,
            start_time=process_create_time(proc.pid),
        )
        save_state(profile, state)
    emit_human(f"project up: {DEFAULT_FRONTEND_URL} + {DEFAULT_BACKEND_URL} (PID {proc.pid})")


def _terminate_failed_boot(proc: subprocess.Popen[bytes]) -> None:
    """Terminate a child that failed to reach health."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)


@app.command("down")
def down(
    force: bool = typer.Option(False, "--force", help="Send SIGKILL immediately."),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Stop the tracked full-project dev process."""
    _stop_project(force=force, profile=profile)


def _stop_project(*, force: bool, profile: str) -> None:
    """Stop the tracked full-project dev process with plain Python parameters."""
    state = load_state(profile)
    if state is None:
        emit_human("no project process tracked")
        return
    stop_project_state(state, force=force)
    delete_state(profile)
    emit_human("stopped")


@app.command("status")
def status(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
    plain: bool = typer.Option(False, "--plain", help="TSV: pid status frontend backend."),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Report the tracked project's process and service health."""
    require_one_output_mode(json_out=json_out, plain=plain)
    payload = _status_payload(load_state(profile))
    _emit_project_payload(payload, json_out=json_out, plain=plain)
    if payload["tracked"] and payload["status"] == "stopped":
        raise typer.Exit(code=EXIT_DEV_DEAD)


@app.command("preflight")
def preflight(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
    plain: bool = typer.Option(False, "--plain", help="TSV: name status message hint."),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Check whether this environment can run the full local project.

    Examples:
      paw project preflight
      paw project preflight --json
      paw project preflight --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    checks = run_preflight_checks(profile=profile)
    emit_preflight(checks, json_out=json_out, plain=plain)
    exit_if_preflight_failed(checks)


@app.command("logs")
def logs(
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Print the detached project log path."""
    state = load_state(profile)
    path = state.log_path if state is not None else str(project_log_path(profile))
    emit_human(path)


def run_project() -> None:
    """Alias for ``paw project up``."""
    _start_project(restart=False, boot_timeout=DEFAULT_BOOT_TIMEOUT_S, profile=DEFAULT_PROFILE)


def stop_project() -> None:
    """Alias for ``paw project down``."""
    _stop_project(force=False, profile=DEFAULT_PROFILE)


@env_app.command("check")
def env_check(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
    plain: bool = typer.Option(False, "--plain", help="TSV: name status message hint."),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Check the local environment needed by Pawrrtal CLI workflows.

    Examples:
      paw env check
      paw env check --json
      paw env check --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    checks = run_preflight_checks(profile=profile)
    emit_preflight(checks, json_out=json_out, plain=plain)
    exit_if_preflight_failed(checks)
