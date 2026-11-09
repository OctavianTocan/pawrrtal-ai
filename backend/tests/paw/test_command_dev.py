"""Tests for ``paw dev`` — local backend process lifecycle.

The real uvicorn binary is never invoked. ``subprocess.Popen`` is
monkeypatched to return a fake process and ``httpx.get`` to return a
fake health response. ``os.kill`` / ``os.killpg`` are stubbed so the
suite never sends a real signal.
"""

from __future__ import annotations

import json
import signal
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from app.cli.paw import config as paw_config
from app.cli.paw.commands.dev import commands as dev_commands_module
from app.cli.paw.commands.dev import process as process_module
from app.cli.paw.commands.dev import state as state_module
from app.cli.paw.errors import EXIT_DEV_DEAD
from app.cli.paw.main import app


@dataclass
class _FakeResponse:
    """Stand-in for ``httpx.Response`` accepted by ``probe_health``."""

    status_code: int


class _FakePopen:
    """Minimal stand-in for ``subprocess.Popen`` used by ``paw dev up``."""

    def __init__(self, pid: int = 12345) -> None:
        self.pid = pid
        self._returncode: int | None = None

    def poll(self) -> int | None:
        return self._returncode


@pytest.fixture
def fake_popen(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record subprocess.Popen calls and return a fake process."""
    calls: list[dict[str, Any]] = []

    def fake_spawn(**kwargs: Any) -> _FakePopen:
        calls.append(kwargs)
        return _FakePopen(pid=12345)

    monkeypatch.setattr(process_module, "spawn_uvicorn", fake_spawn)
    return calls


@pytest.fixture
def healthy_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake the health endpoint as immediately returning HTTP 200."""

    def fake_get(url: str, **_: Any) -> _FakeResponse:
        return _FakeResponse(status_code=200)

    monkeypatch.setattr(httpx, "get", fake_get)


@pytest.fixture
def unhealthy_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake the health endpoint as always raising a connect error."""

    def fake_get(url: str, **_: Any) -> _FakeResponse:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", fake_get)


@pytest.fixture
def alive_pids(monkeypatch: pytest.MonkeyPatch) -> set[int]:
    """Track which PIDs ``pid_alive`` should report as alive."""
    alive: set[int] = set()

    def fake_pid_alive(pid: int) -> bool:
        return pid in alive

    monkeypatch.setattr(process_module, "pid_alive", fake_pid_alive)
    return alive


@pytest.fixture
def killed_pids(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Record every ``os.killpg`` call and no-op the side effect."""
    import os as os_module

    sent: list[tuple[int, int]] = []

    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))

    monkeypatch.setattr(os_module, "killpg", fake_killpg)
    return sent


@pytest.fixture
def fast_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the poll cadences so ``--no-detach``-less tests don't hang on edge cases."""
    monkeypatch.setattr(process_module, "HEALTH_PROBE_INTERVAL_S", 0.0)
    monkeypatch.setattr(process_module, "LIVENESS_POLL_INTERVAL_S", 0.0)


@pytest.fixture
def stable_process_create_time(monkeypatch: pytest.MonkeyPatch) -> dict[int, float]:
    """Fake ``process_create_time`` so PID-recycle checks pass for tracked PIDs.

    Returns a dict keyed by PID; tests can pre-populate it to control what
    the recycle check sees. By default, any PID we spawn returns a fixed
    epoch so the persisted state's ``start_time`` matches on read.
    """
    times: dict[int, float] = {}

    def fake_create_time(pid: int) -> float | None:
        return times.get(pid)

    monkeypatch.setattr(process_module, "process_create_time", fake_create_time)
    # Seed the canonical fake PID used by ``_FakePopen`` so ``paw dev up``
    # writes a non-None start_time and subsequent ``paw dev down`` calls
    # see a matching live value.
    times[12345] = 1_000_000.0
    times[67890] = 2_000_000.0
    return times


def test_up_writes_state_file_and_reports_success(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
):
    """`paw dev up` spawns uvicorn, waits for health, persists the state file."""
    result = runner.invoke(app, ["dev", "up"])
    assert result.exit_code == 0, result.stdout
    assert "backend up on http://127.0.0.1:8000" in result.stdout
    assert "PID 12345" in result.stdout

    state_path = paw_config.profile_dir("default") / "dev.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert state["pid"] == 12345
    assert state["port"] == 8000
    assert state["host"] == "127.0.0.1"
    assert state["schema_version"] == state_module.DEV_STATE_SCHEMA_VERSION
    assert "started_at" in state
    assert state["log_path"].endswith("dev.log")


def test_up_when_already_running_returns_exit_one(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
):
    """A second ``paw dev up`` without ``--restart`` fails with exit 1."""
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    result = runner.invoke(app, ["dev", "up"])
    assert result.exit_code == 1
    # State file still describes the first launch.
    state_path = paw_config.profile_dir("default") / "dev.json"
    assert json.loads(state_path.read_text())["pid"] == 12345


def test_up_restart_stops_old_and_starts_new(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
    stable_process_create_time,
    monkeypatch,
):
    """`paw dev up --restart` SIGTERMs the old PID before launching."""
    import os as os_module

    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    # Switch the spawn mock to return a different PID for the second boot.
    def fake_spawn_2(**_: Any) -> _FakePopen:
        return _FakePopen(pid=67890)

    monkeypatch.setattr(process_module, "spawn_uvicorn", fake_spawn_2)

    sent: list[tuple[int, int]] = []

    # After SIGTERM, simulate the old process dying.
    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        if sig == signal.SIGTERM:
            alive_pids.discard(pid)

    monkeypatch.setattr(os_module, "killpg", fake_killpg)

    result = runner.invoke(app, ["dev", "up", "--restart"])
    assert result.exit_code == 0, result.stdout
    assert any(sig == signal.SIGTERM for _, sig in sent)

    state_path = paw_config.profile_dir("default") / "dev.json"
    assert json.loads(state_path.read_text())["pid"] == 67890


def test_up_boot_timeout_when_health_never_responds(
    runner,
    fake_popen,
    unhealthy_backend,
    alive_pids,
    killed_pids,
    fast_polls,
    monkeypatch,
):
    """`paw dev up` fails with exit 1 if /api/v1/health never responds."""
    monkeypatch.setattr(process_module, "DEFAULT_BOOT_TIMEOUT_S", 1)
    result = runner.invoke(app, ["dev", "up", "--boot-timeout", "1"])
    assert result.exit_code == 1
    # The child should be torn down so we don't leak a half-booted process.
    assert any(sig == signal.SIGTERM for _, sig in killed_pids)
    # No state file should be written when boot fails.
    state_path = paw_config.profile_dir("default") / "dev.json"
    assert not state_path.exists()


def test_down_sigterms_and_removes_state(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
    stable_process_create_time,
    monkeypatch,
):
    """`paw dev down` sends SIGTERM and deletes the state file."""
    import os as os_module

    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    sent: list[tuple[int, int]] = []

    # SIGTERM should "kill" the process in our fake.
    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        if sig in (signal.SIGTERM, signal.SIGKILL):
            alive_pids.discard(pid)

    monkeypatch.setattr(os_module, "killpg", fake_killpg)

    result = runner.invoke(app, ["dev", "down"])
    assert result.exit_code == 0
    assert "stopped" in result.stdout
    assert (12345, signal.SIGTERM) in sent

    state_path = paw_config.profile_dir("default") / "dev.json"
    assert not state_path.exists()


def test_down_when_not_tracked_is_idempotent(runner):
    """`paw dev down` with no state file exits 0 and reports the no-op."""
    result = runner.invoke(app, ["dev", "down"])
    assert result.exit_code == 0
    assert "no dev backend tracked" in result.stdout


def test_down_force_sends_sigkill_immediately(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    killed_pids,
    fast_polls,
    stable_process_create_time,
):
    """`paw dev down --force` skips SIGTERM and sends SIGKILL right away."""
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    result = runner.invoke(app, ["dev", "down", "--force"])
    assert result.exit_code == 0
    sigs = [sig for pid, sig in killed_pids if pid == 12345]
    assert signal.SIGKILL in sigs
    assert signal.SIGTERM not in sigs


def test_status_when_tracked_and_healthy(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
):
    """`paw dev status` reports a running backend."""
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    result = runner.invoke(app, ["dev", "status"])
    assert result.exit_code == 0
    assert "status: running" in result.stdout
    assert "12345" in result.stdout
    assert "127.0.0.1:8000" in result.stdout


def test_status_when_tracked_but_pid_dead(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
):
    """`paw dev status` exits EXIT_DEV_DEAD (7) when the recorded PID is no longer alive."""
    runner.invoke(app, ["dev", "up"])
    # alive_pids is empty -> PID is dead.

    result = runner.invoke(app, ["dev", "status"])
    assert result.exit_code == EXIT_DEV_DEAD
    # Exit 7 must remain distinct from 4 (BackendUnreachableError) so callers
    # can tell "tracked process died" from "couldn't reach backend".
    assert EXIT_DEV_DEAD == 7
    assert "stopped" in result.stdout


def test_status_json_schema(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
):
    """`paw dev status --json` emits the expected structured payload."""
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    result = runner.invoke(app, ["dev", "status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    expected_keys = {
        "tracked",
        "pid",
        "host",
        "port",
        "started_at",
        "uptime",
        "uptime_s",
        "log_path",
        "pid_alive",
        "healthy",
        "status",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["tracked"] is True
    assert payload["pid"] == 12345
    assert payload["status"] == "running"
    assert isinstance(payload["uptime_s"], int)


def test_status_plain_emits_single_tsv_row(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
):
    """`paw dev status --plain` emits a single TSV row: pid\tport\tuptime_s\thealth."""
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    result = runner.invoke(app, ["dev", "status", "--plain"])
    assert result.exit_code == 0
    line = result.stdout.strip().splitlines()[-1]
    columns = line.split("\t")
    assert len(columns) == 4
    pid_col, port_col, uptime_col, health_col = columns
    assert pid_col == "12345"
    assert port_col == "8000"
    # uptime_s must be a stringified integer.
    assert uptime_col.isdigit()
    assert health_col == "ok"


def test_status_plain_untracked_row(runner, monkeypatch):
    """`paw dev status --plain` with no state emits an ``untracked`` health row."""
    monkeypatch.setattr(process_module, "port_in_use", lambda host, port: False)
    result = runner.invoke(app, ["dev", "status", "--plain"])
    assert result.exit_code == 0
    # Avoid ``.strip()`` — the leading-empty pid column is significant.
    line = result.stdout.rstrip("\n").splitlines()[-1]
    columns = line.split("\t")
    assert len(columns) == 4
    assert columns[0] == ""  # pid
    assert columns[1] == "8000"  # port
    assert columns[2] == ""  # uptime_s
    assert columns[3] == "untracked"


def test_status_rejects_json_and_plain_together(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    fast_polls,
):
    """`paw dev status --json --plain` exits 1 — mutually exclusive."""
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    result = runner.invoke(app, ["dev", "status", "--json", "--plain"])
    assert result.exit_code == 1


def test_status_untracked_probes_port(runner, monkeypatch):
    """`paw dev status` with no state file probes the canonical port."""
    monkeypatch.setattr(process_module, "port_in_use", lambda host, port: False)
    result = runner.invoke(app, ["dev", "status"])
    assert result.exit_code == 0
    assert "untracked" in result.stdout


def test_status_untracked_json_flags_port_in_use(runner, monkeypatch):
    """The untracked JSON payload includes ``port_in_use`` for diagnosis."""
    monkeypatch.setattr(process_module, "port_in_use", lambda host, port: True)
    result = runner.invoke(app, ["dev", "status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["tracked"] is False
    assert payload["port_in_use"] is True
    assert payload["status"] == "untracked"


def test_spawn_uvicorn_reload_excludes_log_and_state_files(monkeypatch):
    """The real spawn_uvicorn command line includes --reload-exclude (review M2).

    Bypasses the ``fake_popen`` fixture so the actual command builder runs.
    Intercepts ``subprocess.Popen`` to capture argv without launching uvicorn.
    """
    import subprocess

    captured: dict[str, Any] = {}

    class _PopenStub:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["argv"] = args[0]
            self.pid = 99999

    monkeypatch.setattr(subprocess, "Popen", _PopenStub)
    proc = process_module.spawn_uvicorn(host="127.0.0.1", port=8000, reload=True, log_handle=0)
    assert proc.pid == 99999
    argv = captured["argv"]
    # Defensive: log files + state JSON must not retrigger the watcher.
    assert "--reload-exclude" in argv
    assert "*.log" in argv
    assert "dev.json" in argv


def test_graceful_shutdown_timeout_raised_for_sse_drain():
    """Graceful timeout is 30s, not 10s (review M9 — SSE drain headroom)."""
    assert process_module.GRACEFUL_SHUTDOWN_TIMEOUT_S == 30


def test_dev_help_renders(runner):
    """`paw dev --help` exits 0 and lists the three verbs."""
    result = runner.invoke(app, ["dev", "--help"])
    assert result.exit_code == 0
    for verb in ("up", "down", "status"):
        assert verb in result.stdout


def test_status_help_renders(runner):
    """`paw dev status --help` exits 0 and documents --plain."""
    import re

    result = runner.invoke(app, ["dev", "status", "--help"])
    assert result.exit_code == 0
    # Rich Click colorises help output, so ``--plain`` is rendered as
    # interleaved ANSI escape codes that defeat a literal substring match.
    # Strip the codes before asserting.
    plain_stdout = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--plain" in plain_stdout


def test_dev_down_refuses_when_pid_recycled(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    killed_pids,
    fast_polls,
    stable_process_create_time,
    monkeypatch,
):
    """``paw dev down`` must NOT signal a PID whose live create-time
    diverges from the persisted ``start_time``.

    Simulates PID recycling: we ``paw dev up`` to write a state file with
    ``start_time=1_000_000``, then mutate the fake create-time table so
    the live process reports a different (much later) value. The
    subsequent ``paw dev down`` must:

    1. See the PID is alive (``alive_pids`` still contains it).
    2. Detect the start-time mismatch and refuse to signal.
    3. NOT call ``os.killpg`` for that PID.
    """
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    # Recycle the PID: the live process now reports a creation time
    # one hour later than what we persisted.
    stable_process_create_time[12345] = 1_000_000.0 + 3600.0

    result = runner.invoke(app, ["dev", "down"])
    # The command completes (state file is still removed) but the
    # signal is suppressed and a warning is logged.
    assert result.exit_code == 0
    assert all(pid != 12345 for pid, _sig in killed_pids), killed_pids


def test_dev_down_refuses_when_start_time_missing(
    runner,
    fake_popen,
    healthy_backend,
    alive_pids,
    killed_pids,
    fast_polls,
    monkeypatch,
):
    """A missing ``start_time`` triggers the safe refusal too.

    Without a persisted creation time we can't verify the PID is still
    ours, so the conservative default is to leave the live process
    alone and let the operator clean up the stale state file by hand.
    """
    # No ``stable_process_create_time`` fixture — paw dev up persists
    # ``start_time=None`` because ``process_create_time`` is unmocked
    # and ``ps`` does not find PID 12345 in the test process tree.
    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    result = runner.invoke(app, ["dev", "down"])
    assert result.exit_code == 0
    assert all(pid != 12345 for pid, _sig in killed_pids), killed_pids


def test_kill_failed_boot_terminates_then_kills_child(monkeypatch):
    """``kill_failed_boot`` SIGTERMs, then SIGKILLs, then awaits proc.wait.

    Earlier the function fired-and-forgot SIGTERM, leaving the child's
    zombie unreaped. Now it waits ``FAILED_BOOT_TERMINATE_GRACE_S`` and
    escalates to SIGKILL if the child doesn't exit cleanly.
    """
    import os as os_module

    sent_signals: list[int] = []

    def fake_killpg(pid: int, sig: int) -> None:
        sent_signals.append(sig)

    monkeypatch.setattr(os_module, "killpg", fake_killpg)
    monkeypatch.setattr(process_module, "LIVENESS_POLL_INTERVAL_S", 0.0)
    monkeypatch.setattr(process_module, "FAILED_BOOT_TERMINATE_GRACE_S", 0.05)

    class _NeverDiesPopen:
        pid = 54321
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return 0

    # ``kill_failed_boot`` only touches the poll/pid/wait surface; we
    # type-erase the stub through ``object`` so mypy doesn't require a
    # full ``subprocess.Popen[bytes]`` shape that this test doesn't need.
    process_module.kill_failed_boot(_NeverDiesPopen())  # type: ignore[arg-type]
    assert signal.SIGTERM in sent_signals
    assert signal.SIGKILL in sent_signals


def test_dev_commands_module_re_exported_app_matches(runner):
    """``app.cli.paw.commands.dev.app`` matches the Typer app on the commands module.

    Verifies the package ``__init__`` re-exports the Typer instance so
    ``main.py``'s existing ``app.add_typer(dev_cmd.app, ...)`` call keeps
    working without changes to the registration site.
    """
    from app.cli.paw.commands import dev as dev_pkg

    assert dev_pkg.app is dev_commands_module.app
