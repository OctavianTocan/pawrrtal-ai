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

import app.cli.paw.commands.project.cloudflared as cloudflared_module
import app.cli.paw.commands.project.service as service_module
from app.cli.paw import config as paw_config
from app.cli.paw.commands.project import cli as project_module
from app.cli.paw.commands.project.cloudflared_state import CloudflaredState, save_state
from app.cli.paw.commands.project.preflight import PreflightCheck
from app.cli.paw.commands.project.state import PROJECT_STATE_SCHEMA_VERSION, repo_root
from app.cli.paw.errors import LocalError
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
    assert "http://localhost:3000" in result.stdout
    assert "http://127.0.0.1:8000" in result.stdout

    assert len(fake_project_spawn) == 1
    state_path = paw_config.profile_dir("default") / "project.json"
    state = json.loads(state_path.read_text())
    assert state["pid"] == 23456
    assert state["frontend_url"] == "http://localhost:3000"
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
    """Capture systemctl calls and isolate the generated system unit."""
    calls: list[list[str]] = []
    monkeypatch.setenv("PAWRRTAL_SYSTEMD_UNIT_DIR", str(tmp_path / "systemd"))
    monkeypatch.setattr(service_module, "_require_binary", lambda name: f"/fake/bin/{name}")

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(service_module, "_run", fake_run)
    return calls


def test_project_service_install_writes_system_unit_and_enables_now(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """``paw project service install`` installs and starts a production systemd unit."""
    result = runner.invoke(app, ["project", "service", "install"])
    assert result.exit_code == 0, result.stdout

    unit_path = tmp_path / "systemd" / "pawrrtal.service"
    unit = unit_path.read_text()
    assert f"WorkingDirectory={repo_root()}" in unit
    assert f"EnvironmentFile=-{repo_root() / 'backend/.env'}" in unit
    assert "ExecStart=/fake/bin/bun run serve.ts" in unit
    assert "RestartSec=15" in unit
    assert "KillMode=control-group" in unit
    assert "StartLimitBurst=3" in unit
    assert (
        'Environment="PATH=/fake/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"'
    ) in unit
    assert 'Environment="NODE_ENV=production"' in unit
    assert 'Environment="ENV=prod"' in unit
    assert 'Environment="PAWRRTAL_BACKEND_HOST=127.0.0.1"' in unit
    assert 'Environment="PAWRRTAL_BACKEND_PORT=8000"' in unit
    assert 'Environment="BACKEND_INTERNAL_URL=http://127.0.0.1:8000"' in unit
    assert fake_systemd == [
        ["systemctl", "is-system-running"],
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "pawrrtal.service"],
    ]


def test_project_service_install_can_enable_dev_login(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """``--enable-dev-login`` explicitly exposes the shortcut in production."""
    result = runner.invoke(app, ["project", "service", "install", "--enable-dev-login"])
    assert result.exit_code == 0, result.stdout

    unit_path = tmp_path / "systemd" / "pawrrtal.service"
    unit = unit_path.read_text()
    assert 'Environment="PAWRRTAL_ENABLE_DEV_LOGIN=true"' in unit


def test_project_service_install_allows_saved_cloudflared_origin(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """The managed service records the saved Cloudflared public hostname."""
    save_state(
        CloudflaredState(
            schema_version=1,
            tunnel_name="pawrrtal",
            tunnel_id="tunnel-uuid",
            hostname="pawrrtal.example.com",
            public_url="https://pawrrtal.example.com/",
            config_path="/etc/cloudflared/config.yml",
            credentials_file="/etc/cloudflared/tunnel-uuid.json",
            frontend_origin="http://127.0.0.1:3000",
            backend_origin="http://127.0.0.1:8000",
            metrics="127.0.0.1:20241",
            installed_at="2026-06-07T00:00:00+00:00",
        )
    )

    result = runner.invoke(app, ["project", "service", "install"])
    assert result.exit_code == 0, result.stdout

    unit_path = tmp_path / "systemd" / "pawrrtal.service"
    unit = unit_path.read_text()
    assert 'Environment="PAWRRTAL_PUBLIC_HOSTNAME=pawrrtal.example.com"' in unit


def test_project_service_install_can_start_without_enable(
    runner: CliRunner,
    fake_systemd: list[list[str]],
) -> None:
    """``--no-enable --now`` starts the unit without enabling boot startup."""
    result = runner.invoke(app, ["project", "service", "install", "--no-enable", "--now"])
    assert result.exit_code == 0, result.stdout
    assert ["systemctl", "start", "pawrrtal.service"] in fake_systemd


@pytest.fixture
def fake_cloudflared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    """Capture cloudflared/systemctl calls and isolate tunnel credentials."""
    calls: list[list[str]] = []
    home = tmp_path / "home"
    credentials_dir = home / ".cloudflared"
    credentials_dir.mkdir(parents=True)
    (credentials_dir / "tunnel-uuid.json").write_text('{"secret":"super-secret"}')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cloudflared_module, "_require_binary", lambda name: f"/fake/bin/{name}")
    monkeypatch.setattr(cloudflared_module, "_probe_origin", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        cloudflared_module,
        "_public_access_probe",
        lambda hostname: cloudflared_module.PublicAccessProbe(
            url=f"https://{hostname}/",
            status_code=302,
            location="/cdn-cgi/access/login",
            access_required=True,
        ),
    )

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        stdout = "ok\n"
        if args == ["cloudflared", "tunnel", "list", "--output", "json"]:
            stdout = '[{"name":"pawrrtal","id":"tunnel-uuid"}]\n'
        if args == ["cloudflared", "--version"]:
            stdout = "cloudflared version 2026.6.0\n"
        if args[:2] == ["systemctl", "is-active"]:
            stdout = "active\n"
        if args[:2] == ["systemctl", "is-enabled"]:
            stdout = "enabled\n"
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(cloudflared_module, "_run", fake_run)
    return calls


def test_project_cloudflared_install_writes_ingress_and_starts_service(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    tmp_path: Path,
) -> None:
    """``paw project cloudflared install`` writes the fixed Cloudflared ingress."""
    config_path = tmp_path / "cloudflared" / "config.yml"

    result = runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "install",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    config = config_path.read_text()
    assert "tunnel: tunnel-uuid" in config
    assert f"credentials-file: {config_path.parent}/tunnel-uuid.json" in config
    assert "metrics: 127.0.0.1:20241" in config
    assert "path: ^/api/v1/.*" in config
    assert "path: ^/auth/.*" in config
    assert "path: ^/users/.*" in config
    assert "service: http://127.0.0.1:8000" in config
    assert "service: http://127.0.0.1:3000" in config
    assert "super-secret" not in result.stdout
    assert [
        "cloudflared",
        "--config",
        str(config_path),
        "tunnel",
        "ingress",
        "validate",
    ] in fake_cloudflared
    assert ["cloudflared", "tunnel", "route", "dns", "pawrrtal", "pawrrtal.example.com"] in (
        fake_cloudflared
    )
    assert ["cloudflared", "--config", str(config_path), "service", "install"] in (fake_cloudflared)
    assert ["systemctl", "enable", "--now", "cloudflared"] in fake_cloudflared
    state = json.loads((paw_config.profile_dir("cloudflared") / "project-service.json").read_text())
    assert state["public_url"] == "https://pawrrtal.example.com/"
    assert state["credentials_file"].endswith("tunnel-uuid.json")


def test_project_cloudflared_install_requires_cloudflared(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Install fails before writing config when ``cloudflared`` is absent."""

    def missing_binary(_name: str) -> str:
        raise LocalError("missing")

    monkeypatch.setattr(cloudflared_module, "_require_binary", missing_binary)
    config_path = tmp_path / "cloudflared" / "config.yml"

    result = runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "install",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 1
    assert not config_path.exists()


def test_project_cloudflared_install_rejects_non_loopback_origins(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    tmp_path: Path,
) -> None:
    """The Cloudflared profile refuses to publish non-loopback local origins."""
    result = runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "install",
            "--hostname",
            "pawrrtal.example.com",
            "--frontend-origin",
            "http://192.168.1.2:3000",
            "--config-path",
            str(tmp_path / "cloudflared" / "config.yml"),
        ],
    )

    assert result.exit_code == 1
    assert fake_cloudflared == []


def test_project_cloudflared_install_refuses_invalid_ingress(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Install stops when Cloudflared rejects the generated ingress config."""

    def fail_validate(_config_path: Path) -> None:
        raise LocalError("invalid ingress")

    monkeypatch.setattr(cloudflared_module, "_validate_ingress", fail_validate)

    result = runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "install",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(tmp_path / "cloudflared" / "config.yml"),
        ],
    )

    assert result.exit_code == 1
    assert ["cloudflared", "tunnel", "route", "dns", "pawrrtal", "pawrrtal.example.com"] not in (
        fake_cloudflared
    )


def test_project_cloudflared_verify_requires_access_challenge(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Public verification fails when the hostname serves the app directly."""
    monkeypatch.setattr(
        cloudflared_module,
        "_public_access_probe",
        lambda hostname: cloudflared_module.PublicAccessProbe(
            url=f"https://{hostname}/",
            status_code=200,
            location="",
            access_required=False,
        ),
    )

    result = runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "verify",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(tmp_path / "cloudflared" / "config.yml"),
        ],
    )

    assert result.exit_code == 1
    assert ["cloudflared", "tunnel", "info", "pawrrtal"] in fake_cloudflared


def test_project_cloudflared_verify_reports_access_json(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    tmp_path: Path,
) -> None:
    """Verify emits a stable JSON payload when Access protects the hostname."""
    result = runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "verify",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(tmp_path / "cloudflared" / "config.yml"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["hostname"] == "pawrrtal.example.com"
    assert payload["access_required"] is True
    assert payload["public_status"] == 302


def test_project_cloudflared_verify_uses_saved_install_state(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    tmp_path: Path,
) -> None:
    """Verify reuses saved install flags when the user does not repeat them."""
    config_path = tmp_path / "cloudflared" / "custom.yml"
    runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "install",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(config_path),
            "--frontend-origin",
            "http://127.0.0.1:3000",
            "--backend-origin",
            "http://127.0.0.1:8000",
        ],
    )
    fake_cloudflared.clear()

    result = runner.invoke(app, ["project", "cloudflared", "verify", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["config_path"] == str(config_path)
    assert payload["tunnel_name"] == "pawrrtal"
    assert ["cloudflared", "--config", str(config_path), "tunnel", "ingress", "validate"] in (
        fake_cloudflared
    )
    assert ["cloudflared", "tunnel", "info", "pawrrtal"] in fake_cloudflared


def test_project_cloudflared_status_hides_credentials(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    tmp_path: Path,
) -> None:
    """Status reports operational metadata without printing credentials."""
    config_path = tmp_path / "cloudflared" / "config.yml"
    runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "install",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(config_path),
        ],
    )

    result = runner.invoke(app, ["project", "cloudflared", "status", "--json"])

    assert result.exit_code == 0, result.stdout
    assert "super-secret" not in result.stdout
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["hostname"] == "pawrrtal.example.com"
    assert payload["service_active"] == "active"


def test_project_cloudflared_uninstall_removes_saved_config_path(
    runner: CliRunner,
    fake_cloudflared: list[list[str]],
    tmp_path: Path,
) -> None:
    """Plain uninstall removes the config path recorded by install."""
    config_path = tmp_path / "cloudflared" / "custom.yml"
    runner.invoke(
        app,
        [
            "project",
            "cloudflared",
            "install",
            "--hostname",
            "pawrrtal.example.com",
            "--config-path",
            str(config_path),
        ],
    )
    credentials_path = config_path.parent / "tunnel-uuid.json"

    result = runner.invoke(app, ["project", "cloudflared", "uninstall"])

    assert result.exit_code == 0, result.stdout
    assert not config_path.exists()
    assert not credentials_path.exists()
    assert not (paw_config.profile_dir("cloudflared") / "project-service.json").exists()


def test_project_service_uninstall_disables_and_removes_unit(
    runner: CliRunner,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """``paw project service uninstall`` disables the unit and removes the file."""
    unit_dir = tmp_path / "systemd"
    unit_dir.mkdir(parents=True)
    unit_path = unit_dir / "pawrrtal.service"
    unit_path.write_text("[Unit]\nDescription=old\n")

    result = runner.invoke(app, ["project", "service", "uninstall"])
    assert result.exit_code == 0, result.stdout
    assert not unit_path.exists()
    assert fake_systemd == [
        ["systemctl", "disable", "--now", "pawrrtal.service"],
        ["systemctl", "daemon-reload"],
    ]


def test_project_service_status_invokes_systemctl(
    runner: CliRunner,
    fake_systemd: list[list[str]],
) -> None:
    """``paw project service status`` delegates to the systemd service."""
    result = runner.invoke(app, ["project", "service", "status"])
    assert result.exit_code == 0, result.stdout
    assert fake_systemd == [
        ["systemctl", "status", "pawrrtal.service", "--no-pager"],
    ]
