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
from app.cli.paw.commands import dev as dev_module
from app.cli.paw.main import app


@dataclass
class _FakeResponse:
    """Stand-in for ``httpx.Response`` accepted by ``_probe_health``."""

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

    monkeypatch.setattr(dev_module, "_spawn_uvicorn", fake_spawn)
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
    """Track which PIDs ``_pid_alive`` should report as alive."""
    alive: set[int] = set()

    def fake_pid_alive(pid: int) -> bool:
        return pid in alive

    monkeypatch.setattr(dev_module, "_pid_alive", fake_pid_alive)
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
    monkeypatch.setattr(dev_module, "HEALTH_PROBE_INTERVAL_S", 0.0)
    monkeypatch.setattr(dev_module, "LIVENESS_POLL_INTERVAL_S", 0.0)


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
    assert state["schema_version"] == dev_module.DEV_STATE_SCHEMA_VERSION
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
    monkeypatch,
):
    """`paw dev up --restart` SIGTERMs the old PID before launching."""
    import os as os_module

    runner.invoke(app, ["dev", "up"])
    alive_pids.add(12345)

    # Switch the spawn mock to return a different PID for the second boot.
    def fake_spawn_2(**_: Any) -> _FakePopen:
        return _FakePopen(pid=67890)

    monkeypatch.setattr(dev_module, "_spawn_uvicorn", fake_spawn_2)

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
    monkeypatch.setattr(dev_module, "DEFAULT_BOOT_TIMEOUT_S", 1)
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
    """`paw dev status` exits 4 when the recorded PID is no longer alive."""
    runner.invoke(app, ["dev", "up"])
    # alive_pids is empty -> PID is dead.

    result = runner.invoke(app, ["dev", "status"])
    assert result.exit_code == dev_module.EXIT_TRACKED_BUT_DEAD
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
        "log_path",
        "pid_alive",
        "healthy",
        "status",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["tracked"] is True
    assert payload["pid"] == 12345
    assert payload["status"] == "running"


def test_status_untracked_probes_port(runner, monkeypatch):
    """`paw dev status` with no state file probes the canonical port."""
    monkeypatch.setattr(dev_module, "_port_in_use", lambda host, port: False)
    result = runner.invoke(app, ["dev", "status"])
    assert result.exit_code == 0
    assert "untracked" in result.stdout


def test_status_untracked_json_flags_port_in_use(runner, monkeypatch):
    """The untracked JSON payload includes ``port_in_use`` for diagnosis."""
    monkeypatch.setattr(dev_module, "_port_in_use", lambda host, port: True)
    result = runner.invoke(app, ["dev", "status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["tracked"] is False
    assert payload["port_in_use"] is True
    assert payload["status"] == "untracked"


def test_dev_help_renders(runner):
    """`paw dev --help` exits 0 and lists the three verbs."""
    result = runner.invoke(app, ["dev", "--help"])
    assert result.exit_code == 0
    for verb in ("up", "down", "status"):
        assert verb in result.stdout
