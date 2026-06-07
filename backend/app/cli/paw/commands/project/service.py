"""User systemd service management for the local Pawrrtal dev project."""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from pathlib import Path

import typer

from app.cli.paw.commands.project.cloudflared_state import load_state as load_cloudflared_state
from app.cli.paw.commands.project.state import repo_root
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human

app = typer.Typer(no_args_is_help=True)

SERVICE_NAME = "pawrrtal-dev.service"


def _unit_dir() -> Path:
    """Return the user systemd unit directory."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / "systemd" / "user"


def _unit_path() -> Path:
    """Return the generated service unit path."""
    return _unit_dir() / SERVICE_NAME


def _require_binary(name: str) -> str:
    """Return an absolute binary path or raise an actionable local error."""
    path = shutil.which(name)
    if path is None:
        raise LocalError(f"`{name}` not found on PATH.", hint=f"Install {name}, then retry.")
    return path


def _current_user() -> str:
    """Return the current login name for linger management."""
    return getpass.getuser()


def _systemd_env_line(name: str, value: str) -> str:
    """Return one quoted systemd Environment= line."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'Environment="{name}={escaped}"'


def _next_allowed_dev_origins() -> str:
    """Return explicit or Cloudflared-derived Next dev origins."""
    explicit = os.environ.get("NEXT_ALLOWED_DEV_ORIGINS", "").strip()
    if explicit:
        return explicit
    cloudflared_state = load_cloudflared_state()
    if cloudflared_state is None:
        return ""
    return cloudflared_state.public_url.rstrip("/")


def _unit_text() -> str:
    """Render the user service unit for the current checkout."""
    bun = _require_binary("bun")
    root = repo_root()
    cache_root = root / ".cache"
    path = os.environ.get("PATH", "")
    dev_database_url = os.environ.get("PAWRRTAL_DEV_DATABASE_URL", "")
    next_allowed_dev_origins = _next_allowed_dev_origins()
    env_lines = [
        _systemd_env_line("PATH", path),
        _systemd_env_line("UV_CACHE_DIR", str(cache_root / "uv")),
        _systemd_env_line("XDG_CACHE_HOME", str(cache_root / "xdg")),
        _systemd_env_line("DATABASE_URL", ""),
        _systemd_env_line("PAWRRTAL_DEV_DATABASE_URL", dev_database_url),
        _systemd_env_line("BACKEND_INTERNAL_URL", "http://127.0.0.1:8000"),
    ]
    if next_allowed_dev_origins:
        env_lines.append(_systemd_env_line("NEXT_ALLOWED_DEV_ORIGINS", next_allowed_dev_origins))
    return "\n".join(
        [
            "[Unit]",
            "Description=Pawrrtal local dev server",
            "After=network.target",
            "StartLimitIntervalSec=120",
            "StartLimitBurst=3",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={root}",
            f"ExecStart={bun} run dev.ts",
            "Restart=on-failure",
            "RestartSec=15",
            "KillMode=control-group",
            "TimeoutStopSec=20",
            *env_lines,
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a local service-management command."""
    try:
        result = subprocess.run(args, check=check, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise LocalError(
            f"`{args[0]}` not found on PATH.",
            hint="This service helper requires a Linux host with systemd user services.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        raise LocalError(
            f"`{' '.join(args)}` failed with exit code {exc.returncode}.",
            hint=output or None,
        ) from exc
    return result


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``systemctl --user`` with ``args``."""
    return _run(["systemctl", "--user", *args], check=check)


def _preflight_systemd() -> None:
    """Fail before writing unit files when user systemd is unavailable."""
    result = _systemctl("is-system-running", check=False)
    output = (result.stdout or result.stderr or "").strip()
    if "Failed to connect to bus" in output or "Operation not permitted" in output:
        raise LocalError(
            "User systemd is not available in this environment.",
            hint=output or "Run from a login session with a user systemd bus.",
        )


@app.command("install")
def install(
    enable: bool = typer.Option(True, "--enable/--no-enable", help="Enable the unit."),
    now: bool = typer.Option(True, "--now/--no-now", help="Start the unit after install."),
    linger: bool = typer.Option(
        False,
        "--linger",
        help="Run `loginctl enable-linger` so the user service starts at machine boot.",
    ),
) -> None:
    """Install the Pawrrtal dev server as a user systemd service."""
    _preflight_systemd()
    unit_path = _unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(_unit_text(), encoding="utf-8")
    _systemctl("daemon-reload")
    if enable:
        args = ["enable", SERVICE_NAME]
        if now:
            args.insert(1, "--now")
        _systemctl(*args)
    elif now:
        _systemctl("start", SERVICE_NAME)
    if linger:
        _run(["loginctl", "enable-linger", _current_user()])
    emit_human(f"installed {SERVICE_NAME} at {unit_path}")


@app.command("uninstall")
def uninstall() -> None:
    """Disable and remove the Pawrrtal dev server user systemd service."""
    _systemctl("disable", "--now", SERVICE_NAME)
    unit_path = _unit_path()
    unit_path.unlink(missing_ok=True)
    _systemctl("daemon-reload")
    emit_human(f"removed {SERVICE_NAME}")


@app.command("start")
def start() -> None:
    """Start the user systemd service."""
    _systemctl("start", SERVICE_NAME)
    emit_human(f"started {SERVICE_NAME}")


@app.command("stop")
def stop() -> None:
    """Stop the user systemd service."""
    _systemctl("stop", SERVICE_NAME)
    emit_human(f"stopped {SERVICE_NAME}")


@app.command("restart")
def restart() -> None:
    """Restart the user systemd service."""
    _systemctl("restart", SERVICE_NAME)
    emit_human(f"restarted {SERVICE_NAME}")


@app.command("status")
def status() -> None:
    """Show user systemd service status."""
    result = _systemctl("status", SERVICE_NAME, "--no-pager", check=False)
    body = (result.stdout or result.stderr).strip()
    emit_human(body)
    raise typer.Exit(code=result.returncode)


@app.command("logs")
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs."),
    lines: int = typer.Option(100, "--lines", min=1, help="Number of log lines to show."),
) -> None:
    """Show journal logs for the user systemd service."""
    args = [
        "journalctl",
        "--user",
        "-u",
        SERVICE_NAME,
        "--no-pager",
        "-n",
        str(lines),
    ]
    if follow:
        args.append("-f")
    result = _run(args, check=False)
    emit_human((result.stdout or result.stderr).strip())
    raise typer.Exit(code=result.returncode)
