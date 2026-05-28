"""uvicorn subprocess spawn, signal, and health-probe helpers for ``paw dev``.

Owns everything that touches a live OS process or socket: PID liveness,
port probing, HTTP /api/v1/health probing, the uvicorn spawn command,
the SIGTERM/SIGKILL escalation flow, and the foreground log tailer.
``state.py`` and ``commands.py`` import from here; nothing here imports
from ``commands.py``.

Functions used across the package (``pid_alive``, ``probe_health``,
``spawn_uvicorn``, etc.) carry no leading underscore so the privacy
rule (``.claude/rules/clean-code/python-module-privacy.md``) holds —
the underscore is reserved for truly module-local helpers.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from app.cli.paw.commands.dev.state import DevState

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

# Time between SIGTERM and the SIGKILL fallback. uvicorn under ``--reload``
# with active SSE consumers needs noticeably longer than a cold worker
# to drain — 10s was too tight in practice and caused frequent
# SIGKILL escalations that may leave persistence incomplete. 30s gives
# realistic time to flush logs, close the listening socket, and notify
# SSE subscribers.
GRACEFUL_SHUTDOWN_TIMEOUT_S = 30

# Interval between liveness polls while waiting for the process to die
# after SIGTERM. 100ms keeps ``paw dev down`` snappy without busy-looping.
LIVENESS_POLL_INTERVAL_S = 0.1

# HTTP status that ``/api/v1/health`` returns when the backend is up. Named
# so the comparison in ``probe_health`` reads as intent, not magic number.
HEALTH_OK_STATUS = 200

# Slop allowed when comparing the persisted ``start_time`` with the live
# process's reported create-time. Keeps us robust to clock granularity
# differences between the spawning thread's wall clock and the OS-reported
# create-time (``ps -o lstart`` rounds to whole seconds on macOS).
PID_RECYCLE_TOLERANCE_S = 1.0

# Wait for a child to exit after SIGTERM during the failed-boot teardown
# before escalating to SIGKILL. Short because a child that never reached
# health has nothing to drain.
FAILED_BOOT_TERMINATE_GRACE_S = 10.0


def process_create_time(pid: int) -> float | None:
    """Return the OS-reported creation time of ``pid`` in seconds since epoch.

    Uses ``ps -o lstart= -p <pid>`` so we don't need a hard dependency
    on ``psutil``. ``lstart`` is supported on both macOS and Linux and
    parses with ``%a %b %d %H:%M:%S %Y``. Returns ``None`` when ``ps``
    is unavailable, the process is gone, or the output doesn't parse —
    callers must treat ``None`` as "cannot verify ownership" and bail.
    """
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        # ``lstart`` example: ``Thu May 28 13:08:15 2026``. Parse as local
        # time to match the wall-clock stamp recorded at spawn.
        parsed = time.strptime(raw, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    return time.mktime(parsed)


def pid_alive(pid: int) -> bool:
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


def port_in_use(host: str, port: int) -> bool:
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


def probe_health(host: str, port: int) -> bool:
    """One-shot probe of ``/api/v1/health``. Returns ``True`` on HTTP 200."""
    try:
        response = httpx.get(_health_url(host, port), timeout=HEALTH_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return response.status_code == HEALTH_OK_STATUS


def wait_for_health(host: str, port: int, timeout_s: int) -> bool:
    """Poll the health endpoint until it responds OK or the timeout elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if probe_health(host, port):
            return True
        time.sleep(HEALTH_PROBE_INTERVAL_S)
    return False


def _backend_dir() -> Path:
    """Locate the ``backend/`` directory relative to this source file.

    ``paw dev up`` spawns uvicorn with ``cwd=backend/`` so the relative
    ``--app-dir`` paths in ``dev.ts`` continue to work.
    """
    # __file__ -> backend/app/cli/paw/commands/dev/process.py
    return Path(__file__).resolve().parents[5]


def spawn_uvicorn(
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
        # ``--reload-exclude`` is defensive: if a user sets ``PAW_CONFIG_DIR``
        # to a path inside this repo, dev.log / dev.json writes would
        # otherwise trigger the watcher in a tight loop. The default
        # config dir lives outside the repo so this is a guardrail, not
        # a fix for a current-default bug (review M2).
        command.extend(
            [
                "--reload",
                "--reload-dir",
                ".",
                "--reload-exclude",
                "*.log",
                "--reload-exclude",
                "dev.json",
            ]
        )
    return subprocess.Popen(
        command,
        cwd=_backend_dir(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def is_pid_recycled(state: DevState) -> bool:
    """Return True if the live process at ``state.pid`` is not our spawned child.

    Compares the live process's OS-reported creation time against the
    value we persisted at spawn. A divergence beyond
    ``PID_RECYCLE_TOLERANCE_S`` means the kernel recycled the PID for an
    unrelated process (we spawned X, X died, the kernel reused X's PID
    for some other program). Signalling such a PID would attack an
    innocent third-party process, so the caller must refuse to signal.

    If we have no recorded ``start_time`` (v1 state file, or psutil-less
    environment where ``process_create_time`` returned ``None``) we
    treat the PID as recycled — the safer default.
    """
    if state.start_time is None:
        return True
    live_start = process_create_time(state.pid)
    if live_start is None:
        return True
    return abs(live_start - state.start_time) > PID_RECYCLE_TOLERANCE_S


def stop_tracked_backend(state: DevState, *, force: bool) -> None:
    """Send the appropriate signal(s) to terminate the tracked backend.

    The child runs in its own process group (see ``spawn_uvicorn``)
    so we signal the group rather than the lead PID — uvicorn's
    ``--reload`` mode forks a reloader supervisor and a worker, and
    signalling only the supervisor leaves the worker orphaned.

    Before signalling, checks the live process's creation time against
    the value persisted at spawn. If the times diverge, the PID has been
    recycled — we refuse to signal and log a warning so the operator
    can clean up the stale state file by hand.
    """
    if not pid_alive(state.pid):
        return

    if is_pid_recycled(state):
        logger.warning(
            "Refusing to signal pid %s — start time does not match persisted state. "
            "The PID was likely recycled. Delete the state file by hand if you're "
            "sure the original process is gone.",
            state.pid,
        )
        return

    signal_to_send = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(state.pid, signal_to_send)
    except ProcessLookupError:
        return

    if force:
        return

    if wait_for_exit(state.pid, GRACEFUL_SHUTDOWN_TIMEOUT_S):
        return

    # Graceful shutdown timed out; escalate.
    try:
        os.killpg(state.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def wait_for_exit(pid: int, timeout_s: int) -> bool:
    """Poll until ``pid`` is no longer alive or ``timeout_s`` elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(LIVENESS_POLL_INTERVAL_S)
    return not pid_alive(pid)


def tail_log_until_exit(proc: subprocess.Popen[bytes], log_path: Path) -> None:
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


def kill_failed_boot(proc: subprocess.Popen[bytes]) -> None:
    """Tear down a child that never became healthy.

    SIGTERMs the process group, waits up to ``FAILED_BOOT_TERMINATE_GRACE_S``
    for the child to exit, then escalates to SIGKILL. Critically: we
    block on ``proc.wait()`` so the Python process never accumulates a
    zombie entry for the failed boot — the previous fire-and-forget
    ``os.killpg(SIGTERM)`` left the child to be reaped lazily, which
    could leak file descriptors on systems where many failed boots
    pile up before the parent exits.
    """
    if proc.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    deadline = time.monotonic() + FAILED_BOOT_TERMINATE_GRACE_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(LIVENESS_POLL_INTERVAL_S)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    try:
        proc.wait(timeout=FAILED_BOOT_TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        logger.warning("Failed-boot child did not exit after SIGKILL", extra={"pid": proc.pid})
