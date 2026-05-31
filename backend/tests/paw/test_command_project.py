"""Tests for ``paw project`` — full local app lifecycle helpers."""

from __future__ import annotations

import json
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

import app.cli.paw.commands.project.service as service_module
from app.cli.paw import config as paw_config
from app.cli.paw.commands.project import cli as project_module
from app.cli.paw.commands.project import service_tailscale
from app.cli.paw.commands.project.preflight import PreflightCheck
from app.cli.paw.commands.project.state import PROJECT_STATE_SCHEMA_VERSION, repo_root
from app.cli.paw.main import app


@dataclass
class _FakeResponse:
    """Stand-in for ``httpx.Response`` accepted by project health probes."""

    status_code: int


class _FakePopen:
    """Minimal stand-in for the detached ``bun run dev.ts`` process."""

    def __init__(self, pid: int = 23456) -> None:
        self.pid = pid
        self._returncode: int | None = None

    def poll(self) -> int | None:
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        self._returncode = 0
        return 0


@pytest.fixture
def fake_project_spawn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record project spawn calls and return a fake process."""
    calls: list[dict[str, Any]] = []

    def fake_spawn(*, log_handle: int) -> _FakePopen:
        calls.append({"log_handle": log_handle})
        return _FakePopen()

    monkeypatch.setattr(project_module, "spawn_project", fake_spawn)
    return calls


@pytest.fixture
def healthy_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake both frontend and backend probes as healthy."""

    def fake_get(url: str, **_: Any) -> _FakeResponse:
        if url.endswith("/api/v1/health"):
            return _FakeResponse(status_code=200)
        return _FakeResponse(status_code=200)

    monkeypatch.setattr(httpx, "get", fake_get)


@pytest.fixture
def alive_pids(monkeypatch: pytest.MonkeyPatch) -> set[int]:
    """Track which PIDs the project command should report as alive."""
    alive: set[int] = set()

    def fake_pid_alive(pid: int) -> bool:
        return pid in alive

    monkeypatch.setattr(project_module, "pid_alive", fake_pid_alive)
    return alive


@pytest.fixture
def passing_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make lifecycle tests focus on spawn/stop rather than preflight internals."""

    def fake_preflight(*, profile: str) -> list[PreflightCheck]:
        return [
            PreflightCheck(
                name="env_ready",
                passed=True,
                message="ready",
                hint=None,
            )
        ]

    monkeypatch.setattr(project_module, "run_preflight_checks", fake_preflight)


def test_project_up_starts_full_stack_and_writes_state(
    runner,
    fake_project_spawn,
    healthy_project,
    alive_pids,
    passing_preflight,
):
    """``paw project up`` launches the root dev orchestrator and persists state."""
    result = runner.invoke(app, ["project", "up"])
    assert result.exit_code == 0, result.stdout
    assert "project up" in result.stdout
    assert "http://localhost:53001" in result.stdout
    assert "http://127.0.0.1:8000" in result.stdout

    assert len(fake_project_spawn) == 1
    state_path = paw_config.profile_dir("default") / "project.json"
    state = json.loads(state_path.read_text())
    assert state["pid"] == 23456
    assert state["frontend_url"] == "http://localhost:53001"
    assert state["backend_url"] == "http://127.0.0.1:8000"
    assert state["schema_version"] == PROJECT_STATE_SCHEMA_VERSION
    assert state["log_path"].endswith("project.log")


def test_project_up_runs_preflight_before_spawning(
    runner,
    fake_project_spawn,
    healthy_project,
    monkeypatch,
):
    """``paw project up`` fails fast when preflight fails and does not spawn."""

    def fake_preflight(*, profile: str) -> list[PreflightCheck]:
        return [
            PreflightCheck(
                name="paw_config_dir_writable",
                passed=False,
                message="not writable",
                hint="Set PAW_CONFIG_DIR to a writable directory.",
            )
        ]

    monkeypatch.setattr(project_module, "run_preflight_checks", fake_preflight)

    result = runner.invoke(app, ["project", "up"])
    assert result.exit_code == 1
    assert len(fake_project_spawn) == 0


def test_project_up_kills_failed_boot_process_group_after_timeout(
    runner,
    monkeypatch,
    passing_preflight,
):
    """Failed health waits reap the detached process group even if TERM hangs."""
    import os as os_module

    class HungPopen(_FakePopen):
        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(cmd=["bun", "run", "dev.ts"], timeout=timeout or 0.0)

    monkeypatch.setattr(
        project_module,
        "spawn_project",
        lambda *, log_handle: HungPopen(pid=34567),
    )
    monkeypatch.setattr(project_module, "wait_for_project", lambda *_args: False)
    sent: list[tuple[int, int]] = []

    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))

    monkeypatch.setattr(os_module, "killpg", fake_killpg)

    result = runner.invoke(app, ["project", "up", "--boot-timeout", "1"])

    assert result.exit_code == 1
    assert (34567, signal.SIGTERM) in sent
    assert (34567, signal.SIGKILL) in sent
    assert not (paw_config.profile_dir("default") / "project.json").exists()


def test_project_run_alias_starts_full_stack(
    runner,
    fake_project_spawn,
    healthy_project,
    passing_preflight,
):
    """``paw run`` is a discoverable alias for ``paw project up``."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0, result.stdout
    assert "project up" in result.stdout
    assert len(fake_project_spawn) == 1


def test_project_preflight_json_reports_structured_checks(runner, monkeypatch):
    """``paw project preflight --json`` emits stable check objects."""

    def fake_preflight(*, profile: str) -> list[PreflightCheck]:
        return [
            PreflightCheck(
                name="uv_cache_dir_writable",
                passed=True,
                message="writable",
                hint=None,
            ),
            PreflightCheck(
                name="port_8000_available",
                passed=False,
                message="port is unavailable",
                hint="Stop the existing backend.",
            ),
        ]

    monkeypatch.setattr(project_module, "run_preflight_checks", fake_preflight)

    result = runner.invoke(app, ["project", "preflight", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["checks"][0]["name"] == "uv_cache_dir_writable"
    assert payload["checks"][1]["hint"] == "Stop the existing backend."


def test_project_up_when_already_running_fails_without_restart(
    runner,
    fake_project_spawn,
    healthy_project,
    alive_pids,
    passing_preflight,
):
    """A second ``paw project up`` fails unless ``--restart`` is passed."""
    runner.invoke(app, ["project", "up"])
    alive_pids.add(23456)

    result = runner.invoke(app, ["project", "up"])
    assert result.exit_code == 1


def test_project_down_stops_process_group_and_removes_state(
    runner,
    fake_project_spawn,
    healthy_project,
    alive_pids,
    passing_preflight,
    monkeypatch,
):
    """``paw project down`` terminates the tracked process group."""
    import os as os_module

    runner.invoke(app, ["project", "up"])
    alive_pids.add(23456)
    sent: list[tuple[int, int]] = []

    def fake_killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        alive_pids.discard(pid)

    monkeypatch.setattr(os_module, "killpg", fake_killpg)

    result = runner.invoke(app, ["project", "down"])
    assert result.exit_code == 0
    assert "stopped" in result.stdout
    assert (23456, signal.SIGTERM) in sent
    assert not (paw_config.profile_dir("default") / "project.json").exists()


def test_project_stop_alias_stops_full_stack(
    runner,
    fake_project_spawn,
    healthy_project,
    alive_pids,
    passing_preflight,
    monkeypatch,
):
    """``paw stop`` is a discoverable alias for ``paw project down``."""
    import os as os_module

    runner.invoke(app, ["project", "up"])
    alive_pids.add(23456)
    monkeypatch.setattr(os_module, "killpg", lambda pid, sig: alive_pids.discard(pid))

    result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    assert "stopped" in result.stdout


def test_project_status_json_reports_frontend_and_backend_health(
    runner,
    fake_project_spawn,
    healthy_project,
    alive_pids,
    passing_preflight,
):
    """``paw project status --json`` includes both service health checks."""
    runner.invoke(app, ["project", "up"])
    alive_pids.add(23456)

    result = runner.invoke(app, ["project", "status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "running"
    assert payload["frontend_healthy"] is True
    assert payload["backend_healthy"] is True
    assert payload["pid"] == 23456


def test_project_logs_prints_log_path(
    runner, fake_project_spawn, healthy_project, passing_preflight
):
    """``paw project logs`` shows where the detached dev output is written."""
    runner.invoke(app, ["project", "up"])

    result = runner.invoke(app, ["project", "logs"])
    assert result.exit_code == 0
    assert "project.log" in result.stdout


def test_env_check_json_uses_project_preflight(runner, monkeypatch):
    """``paw env check --json`` is the top-level environment check surface."""

    def fake_preflight(*, profile: str) -> list[PreflightCheck]:
        return [
            PreflightCheck(
                name="bun_available",
                passed=True,
                message="found",
                hint=None,
            )
        ]

    monkeypatch.setattr(project_module, "run_preflight_checks", fake_preflight)

    result = runner.invoke(app, ["env", "check", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "bun_available"


def test_project_env_defaults_to_sqlite(monkeypatch):
    """Global ``DATABASE_URL`` does not leak into local project launches."""
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost:5432/app")
    monkeypatch.delenv("PAWRRTAL_DEV_DATABASE_URL", raising=False)

    env = project_module._project_env()

    assert env["DATABASE_URL"] == ""


def test_project_env_can_opt_into_external_dev_database(monkeypatch):
    """``PAWRRTAL_DEV_DATABASE_URL`` is the explicit non-SQLite dev override."""
    monkeypatch.setenv("DATABASE_URL", "postgres://ignored")
    monkeypatch.setenv("PAWRRTAL_DEV_DATABASE_URL", "postgresql://u:p@localhost:5432/app")

    env = project_module._project_env()

    assert env["DATABASE_URL"] == "postgresql://u:p@localhost:5432/app"


@pytest.fixture
def fake_systemd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    """Capture systemctl/loginctl calls and isolate the generated user unit."""
    calls: list[list[str]] = []
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(service_module, "_require_binary", lambda name: f"/fake/bin/{name}")
    monkeypatch.setattr(service_module, "_current_user", lambda: "octavian")

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(service_module, "_run", fake_run)
    return calls


def test_project_service_install_writes_user_unit_and_enables_now(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """``paw project service install`` installs and starts a user systemd unit."""
    result = runner.invoke(app, ["project", "service", "install"])
    assert result.exit_code == 0, result.stdout

    unit_path = tmp_path / "xdg" / "systemd" / "user" / "pawrrtal-dev.service"
    unit = unit_path.read_text()
    assert f"WorkingDirectory={repo_root()}" in unit
    assert "ExecStart=/fake/bin/bun run dev.ts" in unit
    assert "RestartSec=15" in unit
    assert "KillMode=control-group" in unit
    assert "StartLimitBurst=3" in unit
    assert 'Environment="DATABASE_URL="' in unit
    assert fake_systemd == [
        ["systemctl", "--user", "is-system-running"],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "pawrrtal-dev.service"],
    ]


def test_project_service_install_preserves_explicit_dev_database_url(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service passes the explicit non-SQLite dev DB override to ``dev.ts``."""
    monkeypatch.setenv("PAWRRTAL_DEV_DATABASE_URL", "postgresql://u:p@localhost:5432/app")

    result = runner.invoke(app, ["project", "service", "install"])
    assert result.exit_code == 0, result.stdout

    unit_path = tmp_path / "xdg" / "systemd" / "user" / "pawrrtal-dev.service"
    unit = unit_path.read_text()
    assert 'Environment="DATABASE_URL="' in unit
    assert 'Environment="PAWRRTAL_DEV_DATABASE_URL=postgresql://u:p@localhost:5432/app"' in unit


def test_project_service_install_can_enable_linger(
    runner: CliRunner,
    fake_systemd: list[list[str]],
) -> None:
    """``--linger`` opts into machine-boot startup without an interactive login."""
    result = runner.invoke(app, ["project", "service", "install", "--linger"])
    assert result.exit_code == 0, result.stdout
    assert ["loginctl", "enable-linger", "octavian"] in fake_systemd


def test_project_service_install_tailscale_profile_configures_owned_routes(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Tailscale profile writes profile env and applies owned Serve routes."""

    def fake_tailscale_json(*args: str) -> dict[str, Any]:
        if args == ("status", "--json"):
            return {"Self": {"DNSName": "pawrrtal.example.ts.net."}}
        return {}

    monkeypatch.setattr(service_module, "_tailscale_json", fake_tailscale_json)

    result = runner.invoke(
        app,
        [
            "project",
            "service",
            "install",
            "--profile",
            "tailscale",
            "--tailscale-host",
            "pawrrtal.example.ts.net",
            "--tailscale-port",
            "7447",
        ],
    )

    assert result.exit_code == 0, result.stdout
    unit_path = tmp_path / "xdg" / "systemd" / "user" / "pawrrtal-dev-tailscale.service"
    unit = unit_path.read_text()
    assert 'Environment="NEXT_PUBLIC_BROWSER_API_BASE="' in unit
    assert 'Environment="BACKEND_INTERNAL_URL=http://127.0.0.1:8000"' in unit
    assert 'Environment="NEXT_ALLOWED_DEV_ORIGINS=pawrrtal.example.ts.net,127.0.0.1"' in unit
    assert (
        'Environment="GOOGLE_OAUTH_REDIRECT_URI=https://pawrrtal.example.ts.net:7447/api/v1/auth/oauth/google/callback"'
        in unit
    )
    assert (
        'Environment="APPLE_OAUTH_REDIRECT_URI=https://pawrrtal.example.ts.net:7447/api/v1/auth/oauth/apple/callback"'
        in unit
    )
    assert [
        "tailscale",
        "serve",
        "--bg",
        "--yes",
        "--https",
        "7447",
        "--set-path",
        "/",
        "http://localhost:53001",
    ] in fake_systemd
    assert [
        "tailscale",
        "serve",
        "--bg",
        "--yes",
        "--https",
        "7447",
        "--set-path",
        "/api/v1/",
        "http://127.0.0.1:8000/api/v1/",
    ] in fake_systemd
    state_path = paw_config.profile_dir("tailscale") / "project-service.json"
    state = json.loads(state_path.read_text())
    assert state["public_url"] == "https://pawrrtal.example.ts.net:7447/"


def test_project_service_install_tailscale_refuses_existing_unowned_serve_config(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing unowned Tailscale Serve config is a hard stop."""

    def fake_tailscale_json(*args: str) -> dict[str, Any]:
        if args == ("status", "--json"):
            return {"Self": {"DNSName": "pawrrtal.example.ts.net."}}
        if args == ("serve", "status", "--json"):
            return {
                "Web": {
                    "pawrrtal.example.ts.net:443": {"Handlers": {"/": {"Proxy": "http://other"}}}
                }
            }
        return {}

    monkeypatch.setattr(service_module, "_tailscale_json", fake_tailscale_json)

    result = runner.invoke(
        app,
        [
            "project",
            "service",
            "install",
            "--profile",
            "tailscale",
            "--tailscale-host",
            "pawrrtal.example.ts.net",
        ],
    )

    assert result.exit_code == 1
    assert not any(call[:3] == ["tailscale", "serve", "--bg"] for call in fake_systemd)


def test_project_service_install_tailscale_rejects_other_node_host(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Tailscale profile only installs for the current node's MagicDNS host."""

    def fake_tailscale_json(*args: str) -> dict[str, Any]:
        if args == ("status", "--json"):
            return {"Self": {"DNSName": "openclaw-vps.example.ts.net."}}
        return {}

    monkeypatch.setattr(service_module, "_tailscale_json", fake_tailscale_json)

    result = runner.invoke(
        app,
        [
            "project",
            "service",
            "install",
            "--profile",
            "tailscale",
            "--tailscale-host",
            "pawrrtal.example.ts.net",
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert not any(call[:3] == ["tailscale", "serve", "--bg"] for call in fake_systemd)


def test_project_service_uninstall_tailscale_removes_owned_paths_only(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """Tailscale uninstall removes only after Pawrrtal state says it owns the profile."""
    unit_dir = tmp_path / "xdg" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    unit_path = unit_dir / "pawrrtal-dev-tailscale.service"
    unit_path.write_text("[Unit]\nDescription=old\n")
    state_dir = paw_config.profile_dir("tailscale")
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "project-service.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "tailscale",
                "service_name": "pawrrtal-dev-tailscale.service",
                "installed_at": "2026-05-30T00:00:00+00:00",
                "tailscale_host": "pawrrtal.example.ts.net",
                "tailscale_port": 7447,
                "public_url": "https://pawrrtal.example.ts.net:7447/",
                "routes": [list(route) for route in service_tailscale.TAILSCALE_ROUTES],
            }
        )
    )

    result = runner.invoke(app, ["project", "service", "uninstall", "--profile", "tailscale"])

    assert result.exit_code == 0, result.stdout
    assert not unit_path.exists()
    assert not (state_dir / "project-service.json").exists()
    assert ["tailscale", "serve", "reset"] not in fake_systemd
    assert ["tailscale", "serve", "--https", "7447", "--set-path", "/", "off"] in fake_systemd
    assert [
        "tailscale",
        "serve",
        "--https",
        "7447",
        "--set-path",
        "/api/v1/",
        "off",
    ] in fake_systemd


def test_project_service_commands_reject_unknown_profile(
    runner: CliRunner,
    fake_systemd: list[list[str]],
) -> None:
    """Every service verb rejects profile typos instead of falling back to local."""
    result = runner.invoke(app, ["project", "service", "status", "--profile", "tailcale"])

    assert result.exit_code == 1
    assert fake_systemd == []


def test_project_service_uninstall_disables_and_removes_unit(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """``paw project service uninstall`` disables the unit and removes the file."""
    unit_dir = tmp_path / "xdg" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    unit_path = unit_dir / "pawrrtal-dev.service"
    unit_path.write_text("[Unit]\nDescription=old\n")

    result = runner.invoke(app, ["project", "service", "uninstall"])
    assert result.exit_code == 0, result.stdout
    assert not unit_path.exists()
    assert fake_systemd == [
        ["systemctl", "--user", "disable", "--now", "pawrrtal-dev.service"],
        ["systemctl", "--user", "daemon-reload"],
    ]


def test_project_service_status_invokes_systemctl(
    runner: CliRunner,
    fake_systemd: list[list[str]],
) -> None:
    """``paw project service status`` delegates to the user systemd service."""
    result = runner.invoke(app, ["project", "service", "status"])
    assert result.exit_code == 0, result.stdout
    assert fake_systemd == [
        ["systemctl", "--user", "status", "pawrrtal-dev.service", "--no-pager"],
    ]
