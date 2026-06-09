"""Tests for ``paw services`` system service management."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import app.cli.paw.commands.services.bws as bws_module
import app.cli.paw.commands.services.systemd as systemd_module
from app.cli.paw.commands.project.state import repo_root
from app.cli.paw.main import app


@pytest.fixture
def services_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Provide a local services config with prod/dev Bitwarden project IDs."""
    path = tmp_path / "services.toml"
    path.write_text(
        """
default_target = "prod"

[targets.prod]
bws_project_id = "prod-project"
bws_shared_project_id = "shared-project"

[targets.dev]
bws_project_id = "dev-project"
bws_shared_project_id = "shared-project"
frontend_port = 3100
backend_port = 8100
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PAWRRTAL_SERVICES_CONFIG", str(path))
    return path


@pytest.fixture
def fake_systemd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    """Capture service process calls and isolate generated unit files."""
    calls: list[list[str]] = []
    monkeypatch.setenv("PAWRRTAL_SYSTEMD_UNIT_DIR", str(tmp_path / "systemd"))
    monkeypatch.setattr(systemd_module, "require_binary", lambda name: f"/fake/bin/{name}")

    def fake_run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(systemd_module, "run", fake_run)
    return calls


def test_services_targets_list_json_reports_configured_targets(
    runner: CliRunner,
    services_config: Path,
) -> None:
    """``paw services targets list --json`` emits target metadata."""
    result = runner.invoke(app, ["services", "targets", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["default_target"] == "prod"
    assert {target["name"] for target in payload["targets"]} == {"prod", "dev"}


def test_services_install_requires_yes_or_dry_run(
    runner: CliRunner,
    services_config: Path,
) -> None:
    """Service installs are non-interactive and require an explicit safety flag."""
    result = runner.invoke(app, ["services", "install", "prod"])

    assert result.exit_code == 1


def test_services_install_dry_run_prints_unit_without_writing(
    runner: CliRunner,
    services_config: Path,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """Dry-run install renders the target unit and does not call systemd."""
    result = runner.invoke(app, ["services", "install", "dev", "--dry-run"])

    assert result.exit_code == 0, result.stdout
    assert "Description=Pawrrtal app server (dev)" in result.stdout
    assert "EnvironmentFile=-/etc/pawrrtal/bws.env" in result.stdout
    assert 'Environment="ENV=dev"' in result.stdout
    assert 'Environment="PORT=3100"' in result.stdout
    assert 'Environment="PAWRRTAL_BACKEND_PORT=8100"' in result.stdout
    assert "app.cli.paw.commands.services.launch --target dev" in result.stdout
    assert fake_systemd == []
    assert not (tmp_path / "systemd" / "pawrrtal-dev.service").exists()


def test_services_install_writes_system_unit_and_enables_now(
    runner: CliRunner,
    services_config: Path,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """``paw services install`` installs and starts the selected systemd unit."""
    result = runner.invoke(app, ["services", "install", "prod", "--yes"])

    assert result.exit_code == 0, result.stdout
    unit_path = tmp_path / "systemd" / "pawrrtal.service"
    unit = unit_path.read_text(encoding="utf-8")
    assert f"WorkingDirectory={repo_root()}" in unit
    assert "EnvironmentFile=-/etc/pawrrtal/bws.env" in unit
    assert "ExecStart=/fake/bin/uv run --project backend python -m" in unit
    assert "app.cli.paw.commands.services.launch --target prod" in unit
    assert "RestartSec=15" in unit
    assert "KillMode=control-group" in unit
    assert "SuccessExitStatus=143 130" in unit
    assert "StartLimitBurst=3" in unit
    assert (
        'Environment="PATH=/fake/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"'
    ) in unit
    assert 'Environment="NODE_ENV=production"' in unit
    assert 'Environment="UV_LINK_MODE=copy"' in unit
    assert 'Environment="ENV=prod"' in unit
    assert 'Environment="PAWRRTAL_BACKEND_HOST=127.0.0.1"' in unit
    assert 'Environment="PAWRRTAL_BACKEND_PORT=8000"' in unit
    assert 'Environment="BACKEND_INTERNAL_URL=http://127.0.0.1:8000"' in unit
    assert fake_systemd == [
        ["systemctl", "is-system-running"],
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "pawrrtal.service"],
    ]


def test_services_install_can_start_without_enable(
    runner: CliRunner,
    services_config: Path,
    fake_systemd: list[list[str]],
) -> None:
    """``--no-enable --now`` starts the unit without enabling boot startup."""
    result = runner.invoke(app, ["services", "install", "prod", "--yes", "--no-enable", "--now"])

    assert result.exit_code == 0, result.stdout
    assert ["systemctl", "start", "pawrrtal.service"] in fake_systemd


def test_services_uninstall_requires_yes_or_dry_run(
    runner: CliRunner,
    services_config: Path,
) -> None:
    """Service uninstall does not mutate without --yes or --dry-run."""
    result = runner.invoke(app, ["services", "uninstall", "prod"])

    assert result.exit_code == 1


def test_services_uninstall_disables_and_removes_unit(
    runner: CliRunner,
    services_config: Path,
    fake_systemd: list[list[str]],
    tmp_path: Path,
) -> None:
    """``paw services uninstall`` disables the unit and removes the file."""
    unit_dir = tmp_path / "systemd"
    unit_dir.mkdir(parents=True)
    unit_path = unit_dir / "pawrrtal.service"
    unit_path.write_text("[Unit]\nDescription=old\n", encoding="utf-8")

    result = runner.invoke(app, ["services", "uninstall", "prod", "--yes"])

    assert result.exit_code == 0, result.stdout
    assert not unit_path.exists()
    assert fake_systemd == [
        ["systemctl", "disable", "--now", "pawrrtal.service"],
        ["systemctl", "daemon-reload"],
    ]


def test_services_status_invokes_systemctl(
    runner: CliRunner,
    services_config: Path,
    fake_systemd: list[list[str]],
) -> None:
    """``paw services status`` delegates to the systemd service."""
    result = runner.invoke(app, ["services", "status", "prod"])

    assert result.exit_code == 0, result.stdout
    assert fake_systemd == [["systemctl", "status", "pawrrtal.service", "--no-pager"]]


def test_services_secrets_check_filters_shared_keys_and_hides_values(
    runner: CliRunner,
    services_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secret checks report names only and ignore non-allowlisted shared keys."""
    monkeypatch.setenv("BWS_ACCESS_TOKEN", "token")

    def fake_run_bws(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args[:3] == ["bws", "secret", "list"]
        project_id = args[3]
        assert args[4:] == ["--output", "json"]
        if project_id == "shared-project":
            payload = [
                {"key": "GOOGLE_API_KEY", "value": "shared-google"},
                {"key": "TELEGRAM_CHAT_ID_SECRET_ID", "value": "legacy"},
            ]
        else:
            payload = [
                {"key": "DATABASE_URL", "value": "postgres://secret"},
                {"key": "AUTH_SECRET", "value": "auth-secret"},
                {"key": "WORKSPACE_ENCRYPTION_KEY", "value": "workspace-key"},
                {"key": "TELEGRAM_BOT_TOKEN", "value": "bot-token"},
                {"key": "TELEGRAM_BOT_USERNAME", "value": "bot-name"},
            ]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps(payload))

    monkeypatch.setattr(bws_module, "_run_bws", fake_run_bws)

    result = runner.invoke(app, ["services", "secrets", "check", "prod", "--json"])

    assert result.exit_code == 0, result.stdout
    assert "postgres://secret" not in result.stdout
    assert "shared-google" not in result.stdout
    assert "TELEGRAM_CHAT_ID_SECRET_ID" not in result.stdout
    payload = json.loads(result.stdout)
    assert "GOOGLE_API_KEY" in payload["loaded_keys"]
    assert "DATABASE_URL" in payload["loaded_keys"]


def test_project_service_surface_is_removed(runner: CliRunner) -> None:
    """``paw project service`` is not kept as a compatibility alias."""
    result = runner.invoke(app, ["project", "service", "--help"])

    assert result.exit_code != 0
