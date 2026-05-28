"""``paw dev`` Typer command surface: ``up`` / ``down`` / ``status``.

Wires the persisted state (`state.py`) and the process / health helpers
(`process.py`) to user-facing verbs. This module owns only the CLI
contract — no spawn, no signal, no state-file format details — so the
Typer surface can change without touching orchestration internals.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import typer

from app.cli.paw.commands.dev import process as process_module
from app.cli.paw.commands.dev import state as state_module
from app.cli.paw.commands.dev.process import (
    DEFAULT_BOOT_TIMEOUT_S,
    DEFAULT_DEV_HOST,
    DEFAULT_DEV_PORT,
)
from app.cli.paw.commands.dev.state import DEV_STATE_SCHEMA_VERSION, DevState
from app.cli.paw.config import DEFAULT_PROFILE
from app.cli.paw.errors import EXIT_DEV_DEAD, LocalError
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)


def _require_one_output_mode(*, json_out: bool, plain: bool) -> None:
    """Reject simultaneous --json + --plain. Mutually exclusive by design."""
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
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


def _uptime_seconds(started_at: str) -> int:
    """Return integer seconds since ``started_at`` (0 on parse failure / clock skew)."""
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0
    seconds = int((datetime.now(UTC) - started).total_seconds())
    return max(seconds, 0)


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
    existing = state_module.load_state(profile)
    if (
        existing is not None
        and process_module.pid_alive(existing.pid)
        and process_module.probe_health(existing.host, existing.port)
    ):
        if not restart:
            raise LocalError(
                f"Backend already running (pid {existing.pid}, port {existing.port}).",
                hint="Pass `--restart` to stop the existing process first, or run `paw dev down`.",
            )
        process_module.stop_tracked_backend(existing, force=False)
        state_module.delete_state(profile)

    log_path = state_module.dev_log_path(profile)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")
    try:
        try:
            proc = process_module.spawn_uvicorn(
                host=host,
                port=port,
                reload=reload,
                log_handle=log_handle.fileno(),
            )
        except FileNotFoundError as exc:
            raise LocalError(
                f"Failed to spawn uvicorn: {exc}",
                hint="Ensure `uv` is on PATH and run from a workspace where `uv run uvicorn` works.",
            ) from exc

        if not process_module.wait_for_health(host, port, boot_timeout):
            # Tear the dead child down so we don't leak a half-booted process.
            process_module.kill_failed_boot(proc)
            raise LocalError(
                f"Backend did not become healthy on http://{host}:{port} within {boot_timeout}s.",
                hint=f"Inspect {log_path} for boot errors.",
            )

        # OS-reported start time so ``paw dev down`` can verify the PID
        # is still ours before signalling — see ``is_pid_recycled``.
        start_time = process_module.process_create_time(proc.pid)
        state = DevState(
            schema_version=DEV_STATE_SCHEMA_VERSION,
            pid=proc.pid,
            host=host,
            port=port,
            started_at=datetime.now(UTC).isoformat(),
            log_path=str(log_path),
            start_time=start_time,
        )
        state_module.save_state(profile, state)
    finally:
        # Wrap the entire post-spawn block so the file descriptor is
        # released even if ``wait_for_health`` raises (review M1).
        log_handle.close()

    emit_human(f"backend up on http://{host}:{port} (PID {proc.pid})")

    if not detach:
        process_module.tail_log_until_exit(proc, log_path)


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
    state = state_module.load_state(profile)
    if state is None:
        emit_human("no dev backend tracked")
        return

    process_module.stop_tracked_backend(state, force=force)
    state_module.delete_state(profile)
    emit_human("stopped")


@app.command("status")
def status(
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of human text."),
    plain: bool = typer.Option(
        False,
        "--plain",
        help="Single-row TSV: pid\\tport\\tuptime_s\\thealth.",
    ),
    profile: str = typer.Option(DEFAULT_PROFILE, "--profile"),
) -> None:
    """Report the dev backend's health: PID + port + uptime + /api/v1/health.

    Exits 0 when running or untracked, EXIT_DEV_DEAD (7) when the
    persisted PID exists in state but is no longer alive. Exit 7 is
    distinct from 4 (BackendUnreachable) on purpose: 4 means a network
    probe failed, 7 means the tracked process died — different
    operational situations that warrant different remediation.

    Examples:
      paw dev status
      paw dev status --json
      paw dev status --plain
    """
    _require_one_output_mode(json_out=json_out, plain=plain)

    state = state_module.load_state(profile)
    if state is None:
        untracked = _untracked_status(DEFAULT_DEV_HOST, DEFAULT_DEV_PORT)
        _emit_status(untracked, json_out=json_out, plain=plain)
        return

    pid_is_alive = process_module.pid_alive(state.pid)
    healthy = process_module.probe_health(state.host, state.port) if pid_is_alive else False
    payload: dict[str, Any] = {
        "tracked": True,
        "pid": state.pid,
        "host": state.host,
        "port": state.port,
        "started_at": state.started_at,
        "uptime": _format_uptime(state.started_at),
        "uptime_s": _uptime_seconds(state.started_at),
        "log_path": state.log_path,
        "pid_alive": pid_is_alive,
        "healthy": healthy,
        "status": _classify_status(pid_alive=pid_is_alive, healthy=healthy),
    }

    _emit_status(payload, json_out=json_out, plain=plain)

    if not pid_is_alive:
        raise typer.Exit(code=EXIT_DEV_DEAD)


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
        "port_in_use": process_module.port_in_use(host, port),
        "status": "untracked",
    }


def _emit_status(payload: dict[str, Any], *, json_out: bool, plain: bool) -> None:
    """Dispatch to the right output renderer based on the user's flags."""
    if json_out:
        emit_json(payload)
        return
    if plain:
        _emit_plain_status(payload)
        return
    _emit_human_status(payload)


def _emit_plain_status(payload: dict[str, Any]) -> None:
    r"""Single-row TSV ``pid\tport\tuptime_s\thealth`` for shell pipelines.

    Untracked rows still emit a row (empty pid + uptime) so consumers can
    grep on the health column without special-casing absence.
    """
    if not payload.get("tracked"):
        pid: Any = ""
        uptime_s: Any = ""
        health = "untracked"
    else:
        pid = payload["pid"]
        uptime_s = payload["uptime_s"]
        health = "ok" if payload["healthy"] else "down"
    emit_plain_rows([(pid, payload["port"], uptime_s, health)])


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
