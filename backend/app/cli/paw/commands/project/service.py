"""Systemd service management for the Cloudflared-facing Pawrrtal server."""

from __future__ import annotations

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

SERVICE_NAME = "pawrrtal.service"
DEFAULT_ENV_FILE_NAME = "backend/.env"
STANDARD_SERVICE_PATHS = (
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)


def _unit_dir() -> Path:
    """Return the systemd unit directory."""
    override = os.environ.get("PAWRRTAL_SYSTEMD_UNIT_DIR")
    return Path(override) if override else Path("/etc/systemd/system")


def _unit_path() -> Path:
    """Return the generated service unit path."""
    return _unit_dir() / SERVICE_NAME


def _require_binary(name: str) -> str:
    """Return an absolute binary path or raise an actionable local error."""
    path = shutil.which(name)
    if path is None:
        raise LocalError(f"`{name}` not found on PATH.", hint=f"Install {name}, then retry.")
    return path


def _systemd_env_line(name: str, value: str) -> str:
    """Return one quoted systemd Environment= line."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'Environment="{name}={escaped}"'


def _service_path(binary_paths: list[str]) -> str:
    """Return a stable PATH for the systemd service."""
    entries = [str(Path(binary_path).parent) for binary_path in binary_paths]
    entries.extend(STANDARD_SERVICE_PATHS)
    deduped = list(dict.fromkeys(entries))
    return ":".join(deduped)


def _public_hostname() -> str:
    """Return the saved public hostname, if Cloudflared has been installed."""
    cloudflared_state = load_cloudflared_state()
    if cloudflared_state is None:
        return ""
    return cloudflared_state.hostname.strip()


def _unit_text(*, enable_dev_login: bool, env_file: Path | None) -> str:
    """Render the system service unit for the current checkout."""
    bun = _require_binary("bun")
    uv = _require_binary("uv")
    node = _require_binary("node")
    root = repo_root()
    cache_root = root / ".cache"
    path = _service_path([bun, uv, node])
    public_hostname = _public_hostname()
    env_file_line = f"EnvironmentFile=-{env_file}" if env_file is not None else None
    env_lines = [
        _systemd_env_line("PATH", path),
        _systemd_env_line("UV_CACHE_DIR", str(cache_root / "uv")),
        _systemd_env_line("XDG_CACHE_HOME", str(cache_root / "xdg")),
        _systemd_env_line("NODE_ENV", "production"),
        _systemd_env_line("NEXT_TELEMETRY_DISABLED", "1"),
        _systemd_env_line("ENV", "prod"),
        _systemd_env_line("HOSTNAME", "127.0.0.1"),
        _systemd_env_line("PORT", "3000"),
        _systemd_env_line("PAWRRTAL_BACKEND_HOST", "127.0.0.1"),
        _systemd_env_line("PAWRRTAL_BACKEND_PORT", "8000"),
        _systemd_env_line("BACKEND_INTERNAL_URL", "http://127.0.0.1:8000"),
    ]
    if public_hostname:
        env_lines.append(_systemd_env_line("PAWRRTAL_PUBLIC_HOSTNAME", public_hostname))
    if enable_dev_login:
        env_lines.append(_systemd_env_line("PAWRRTAL_ENABLE_DEV_LOGIN", "true"))
    return "\n".join(
        [
            "[Unit]",
            "Description=Pawrrtal production app server",
            "After=network-online.target",
            "Wants=network-online.target",
            "StartLimitIntervalSec=120",
            "StartLimitBurst=3",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={root}",
            *(line for line in [env_file_line] if line is not None),
            f"ExecStart={bun} run serve.ts",
            "Restart=on-failure",
            "RestartSec=15",
            "KillMode=control-group",
            "TimeoutStopSec=25",
            *env_lines,
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def _resolve_env_file(value: str) -> Path | None:
    """Resolve a service env-file path relative to the active checkout."""
    stripped = value.strip()
    if not stripped:
        return None
    path = Path(stripped).expanduser()
    if not path.is_absolute():
        path = repo_root() / path
    return path


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a local service-management command."""
    try:
        result = subprocess.run(args, check=check, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise LocalError(
            f"`{args[0]}` not found on PATH.",
            hint="This service helper requires a Linux host with systemd.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        raise LocalError(
            f"`{' '.join(args)}` failed with exit code {exc.returncode}.",
            hint=output or None,
        ) from exc
    return result


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``systemctl`` with ``args``."""
    return _run(["systemctl", *args], check=check)


def _preflight_systemd() -> None:
    """Fail before writing unit files when systemd is unavailable."""
    result = _systemctl("is-system-running", check=False)
    output = (result.stdout or result.stderr or "").strip()
    if "Failed to connect to bus" in output or "Operation not permitted" in output:
        raise LocalError(
            "Systemd is not available in this environment.",
            hint=output or "Run on the deployment host with systemd available.",
        )


@app.command("install")
def install(
    enable: bool = typer.Option(True, "--enable/--no-enable", help="Enable the unit."),
    now: bool = typer.Option(True, "--now/--no-now", help="Start the unit after install."),
    enable_dev_login: bool = typer.Option(
        False,
        "--enable-dev-login",
        help="Expose the Dev Admin shortcut in production. Use only behind Cloudflare Access.",
    ),
    env_file: str = typer.Option(
        DEFAULT_ENV_FILE_NAME,
        "--env-file",
        help="Optional backend env file loaded by systemd. Use an empty value to disable.",
    ),
) -> None:
    """Install the Pawrrtal production loopback server as a systemd service."""
    _preflight_systemd()
    resolved_env_file = _resolve_env_file(env_file)
    unit_path = _unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        _unit_text(enable_dev_login=enable_dev_login, env_file=resolved_env_file),
        encoding="utf-8",
    )
    _systemctl("daemon-reload")
    if enable:
        args = ["enable", SERVICE_NAME]
        if now:
            args.insert(1, "--now")
        _systemctl(*args)
    elif now:
        _systemctl("start", SERVICE_NAME)
    emit_human(f"installed {SERVICE_NAME} at {unit_path}")


@app.command("uninstall")
def uninstall() -> None:
    """Disable and remove the Pawrrtal systemd service."""
    _systemctl("disable", "--now", SERVICE_NAME)
    unit_path = _unit_path()
    unit_path.unlink(missing_ok=True)
    _systemctl("daemon-reload")
    emit_human(f"removed {SERVICE_NAME}")


@app.command("start")
def start() -> None:
    """Start the systemd service."""
    _systemctl("start", SERVICE_NAME)
    emit_human(f"started {SERVICE_NAME}")


@app.command("stop")
def stop() -> None:
    """Stop the systemd service."""
    _systemctl("stop", SERVICE_NAME)
    emit_human(f"stopped {SERVICE_NAME}")


@app.command("restart")
def restart() -> None:
    """Restart the systemd service."""
    _systemctl("restart", SERVICE_NAME)
    emit_human(f"restarted {SERVICE_NAME}")


@app.command("status")
def status() -> None:
    """Show systemd service status."""
    result = _systemctl("status", SERVICE_NAME, "--no-pager", check=False)
    body = (result.stdout or result.stderr).strip()
    emit_human(body)
    raise typer.Exit(code=result.returncode)


@app.command("logs")
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs."),
    lines: int = typer.Option(100, "--lines", min=1, help="Number of log lines to show."),
) -> None:
    """Show journal logs for the systemd service."""
    args = [
        "journalctl",
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
