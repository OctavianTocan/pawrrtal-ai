"""User systemd service management for the local Pawrrtal dev project."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import typer

from app.cli.paw.commands.project.service_tailscale import (
    DEFAULT_TAILSCALE_HTTPS_PORT,
    TAILSCALE_ROUTES,
    serve_port_has_config,
    tailscale_origin_label,
    tailscale_public_origin,
    tailscale_self_dns_name,
)
from app.cli.paw.commands.project.state import (
    DEFAULT_BACKEND_URL,
    repo_root,
    service_state_path,
)
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human

app = typer.Typer(no_args_is_help=True)

SERVICE_NAME = "pawrrtal-dev.service"
TAILSCALE_PROFILE = "tailscale"
TAILSCALE_SERVICE_NAME = "pawrrtal-dev-tailscale.service"
SERVICE_STATE_SCHEMA_VERSION = 1
ROUTE_FIELD_COUNT = 2


@dataclass(frozen=True, slots=True)
class ServiceProfileState:
    """Persisted state for a managed project service profile."""

    schema_version: int
    profile: str
    service_name: str
    installed_at: str
    tailscale_host: str | None = None
    tailscale_port: int = DEFAULT_TAILSCALE_HTTPS_PORT
    public_url: str | None = None
    routes: tuple[tuple[str, str], ...] = ()


def _unit_dir() -> Path:
    """Return the user systemd unit directory."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / "systemd" / "user"


def _unit_path(profile: str = "local") -> Path:
    """Return the generated service unit path."""
    return _unit_dir() / _service_name(profile)


def _service_name(profile: str) -> str:
    """Return the systemd unit name for a service profile."""
    return (
        TAILSCALE_SERVICE_NAME if _normalize_profile(profile) == TAILSCALE_PROFILE else SERVICE_NAME
    )


def _normalize_profile(profile: str) -> str:
    """Validate and normalize a service profile name."""
    if profile not in {"local", TAILSCALE_PROFILE}:
        raise LocalError("--profile must be either `local` or `tailscale`.")
    return profile


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


def _unit_text(
    *,
    profile: str = "local",
    tailscale_host: str | None = None,
    tailscale_port: int = DEFAULT_TAILSCALE_HTTPS_PORT,
) -> str:
    """Render the user service unit for the current checkout."""
    bun = _require_binary("bun")
    root = repo_root()
    cache_root = root / ".cache"
    path = os.environ.get("PATH", "")
    dev_database_url = os.environ.get("PAWRRTAL_DEV_DATABASE_URL", "")
    public_origin = tailscale_public_origin(tailscale_host, tailscale_port)
    env_lines = [
        _systemd_env_line("PATH", path),
        _systemd_env_line("UV_CACHE_DIR", str(cache_root / "uv")),
        _systemd_env_line("XDG_CACHE_HOME", str(cache_root / "xdg")),
        _systemd_env_line("DATABASE_URL", ""),
        _systemd_env_line("PAWRRTAL_DEV_DATABASE_URL", dev_database_url),
    ]
    if profile == TAILSCALE_PROFILE:
        env_lines.extend(
            [
                _systemd_env_line("NEXT_PUBLIC_BROWSER_API_BASE", ""),
                _systemd_env_line("BACKEND_INTERNAL_URL", DEFAULT_BACKEND_URL),
                _systemd_env_line("NEXT_ALLOWED_DEV_ORIGINS", tailscale_host or ""),
                _systemd_env_line(
                    "GOOGLE_OAUTH_REDIRECT_URI",
                    f"{public_origin}/api/v1/auth/oauth/google/callback",
                ),
                _systemd_env_line(
                    "APPLE_OAUTH_REDIRECT_URI",
                    f"{public_origin}/api/v1/auth/oauth/apple/callback",
                ),
                _systemd_env_line("OAUTH_POST_LOGIN_REDIRECT", f"{public_origin}/"),
                _systemd_env_line("BACKEND_API_KEY", ""),
            ]
        )
    return "\n".join(
        [
            "[Unit]",
            f"Description=Pawrrtal {profile} dev server",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={root}",
            f"ExecStart={bun} run dev.ts",
            "Restart=on-failure",
            "RestartSec=3",
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


def _run_tailscale(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a Tailscale CLI command."""
    return _run(["tailscale", *args], check=check)


def _tailscale_json(*args: str) -> dict[str, Any]:
    """Run a Tailscale command that emits JSON and parse the result."""
    result = _run_tailscale(*args)
    stdout = result.stdout.strip()
    if not stdout:
        return {}
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LocalError("Tailscale returned invalid JSON.", hint=stdout) from exc
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _normalize_tailscale_host(host: str | None) -> str:
    """Normalize a bare Tailscale hostname or URL to a hostname."""
    candidate = (host or "").strip()
    if not candidate:
        raise LocalError("--tailscale-host is required for --profile tailscale.")
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    if parsed.scheme != "https" or not parsed.hostname:
        raise LocalError("--tailscale-host must be a HTTPS Tailscale hostname.")
    hostname = parsed.hostname.lower()
    if not hostname.endswith(".ts.net"):
        raise LocalError("--tailscale-host must be a .ts.net hostname.")
    return hostname


def _load_service_state(profile: str) -> ServiceProfileState | None:
    """Read service profile state when present."""
    path = service_state_path(profile)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return ServiceProfileState(
        schema_version=int(raw.get("schema_version", SERVICE_STATE_SCHEMA_VERSION)),
        profile=str(raw.get("profile", profile)),
        service_name=str(raw.get("service_name", _service_name(profile))),
        installed_at=str(raw.get("installed_at", "")),
        tailscale_host=raw.get("tailscale_host"),
        tailscale_port=int(raw.get("tailscale_port", DEFAULT_TAILSCALE_HTTPS_PORT)),
        public_url=raw.get("public_url"),
        routes=_load_routes(raw.get("routes", [])),
    )


def _load_routes(raw_routes: object) -> tuple[tuple[str, str], ...]:
    """Return valid persisted ``(path, target)`` route tuples."""
    if not isinstance(raw_routes, list):
        return ()
    routes: list[tuple[str, str]] = []
    for route in raw_routes:
        if not isinstance(route, list | tuple) or len(route) != ROUTE_FIELD_COUNT:
            continue
        path_prefix, target = route
        if isinstance(path_prefix, str) and isinstance(target, str):
            routes.append((path_prefix, target))
    return tuple(routes)


def _save_service_state(profile: str, state: ServiceProfileState) -> None:
    """Persist service profile state."""
    path = service_state_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True), encoding="utf-8")


def _delete_service_state(profile: str) -> None:
    """Remove service profile state if it exists."""
    service_state_path(profile).unlink(missing_ok=True)


def _preflight_tailscale_profile(hostname: str, port: int) -> None:
    """Validate Tailscale Serve can be safely owned by Pawrrtal."""
    if os.environ.get("BACKEND_API_KEY"):
        raise LocalError(
            "The Tailscale profile does not support BACKEND_API_KEY.",
            hint="Use Tailscale ACLs plus Pawrrtal login for this private profile.",
        )
    _require_binary("tailscale")
    status = _tailscale_json("status", "--json")
    self_dns_name = tailscale_self_dns_name(status)
    if self_dns_name != hostname:
        hint = f"This node is {self_dns_name}." if self_dns_name else None
        raise LocalError("--tailscale-host must match this Tailscale node.", hint=hint)
    serve_status = _tailscale_json("serve", "status", "--json")
    has_owned_state = _load_service_state(TAILSCALE_PROFILE) is not None
    if serve_port_has_config(serve_status, hostname=hostname, port=port) and not has_owned_state:
        raise LocalError(
            "Tailscale Serve already has configuration on the requested Pawrrtal origin.",
            hint=(
                f"Inspect `tailscale serve status --json` or choose another "
                f"`--tailscale-port` for {tailscale_origin_label(hostname, port)}."
            ),
        )


def _apply_tailscale_routes(port: int) -> None:
    """Publish local loopback services through Tailscale Serve path routes."""
    for path_prefix, target in TAILSCALE_ROUTES:
        _run_tailscale(
            "serve",
            "--bg",
            "--yes",
            "--https",
            str(port),
            "--set-path",
            path_prefix,
            target,
        )


def _clear_tailscale_routes(port: int) -> None:
    """Remove Pawrrtal-owned Tailscale Serve path routes."""
    for path_prefix, _target in reversed(TAILSCALE_ROUTES):
        _run_tailscale(
            "serve",
            "--https",
            str(port),
            "--set-path",
            path_prefix,
            "off",
            check=False,
        )


@app.command("install")
def install(
    enable: bool = typer.Option(True, "--enable/--no-enable", help="Enable the unit."),
    now: bool = typer.Option(True, "--now/--no-now", help="Start the unit after install."),
    profile: str = typer.Option("local", "--profile", help="Service profile: local or tailscale."),
    tailscale_host: str | None = typer.Option(
        None,
        "--tailscale-host",
        help="Tailscale HTTPS hostname for --profile tailscale, e.g. host.tailnet.ts.net.",
    ),
    tailscale_port: int = typer.Option(
        DEFAULT_TAILSCALE_HTTPS_PORT,
        "--tailscale-port",
        min=1,
        max=65535,
        help="Tailscale HTTPS port for --profile tailscale.",
    ),
    linger: bool = typer.Option(
        False,
        "--linger",
        help="Run `loginctl enable-linger` so the user service starts at machine boot.",
    ),
) -> None:
    """Install the Pawrrtal dev server as a user systemd service."""
    profile = _normalize_profile(profile)
    hostname = _normalize_tailscale_host(tailscale_host) if profile == TAILSCALE_PROFILE else None
    _preflight_systemd()
    if hostname is not None:
        _preflight_tailscale_profile(hostname, tailscale_port)
    unit_path = _unit_path(profile)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        _unit_text(profile=profile, tailscale_host=hostname, tailscale_port=tailscale_port),
        encoding="utf-8",
    )
    _systemctl("daemon-reload")
    service_name = _service_name(profile)
    if enable:
        args = ["enable", service_name]
        if now:
            args.insert(1, "--now")
        _systemctl(*args)
    elif now:
        _systemctl("start", service_name)
    if hostname is not None:
        _apply_tailscale_routes(tailscale_port)
        public_origin = tailscale_public_origin(hostname, tailscale_port)
        _save_service_state(
            profile,
            ServiceProfileState(
                schema_version=SERVICE_STATE_SCHEMA_VERSION,
                profile=profile,
                service_name=service_name,
                installed_at=datetime.now(UTC).isoformat(),
                tailscale_host=hostname,
                tailscale_port=tailscale_port,
                public_url=f"{public_origin}/",
                routes=TAILSCALE_ROUTES,
            ),
        )
    if linger:
        _run(["loginctl", "enable-linger", _current_user()])
    emit_human(f"installed {service_name} at {unit_path}")


@app.command("uninstall")
def uninstall(
    profile: str = typer.Option("local", "--profile", help="Service profile: local or tailscale."),
) -> None:
    """Disable and remove the Pawrrtal dev server user systemd service."""
    profile = _normalize_profile(profile)
    service_name = _service_name(profile)
    _systemctl("disable", "--now", service_name)
    state = _load_service_state(profile)
    if profile == TAILSCALE_PROFILE and state is not None:
        _clear_tailscale_routes(state.tailscale_port)
        _delete_service_state(profile)
    unit_path = _unit_path(profile)
    unit_path.unlink(missing_ok=True)
    _systemctl("daemon-reload")
    emit_human(f"removed {service_name}")


@app.command("start")
def start(profile: str = typer.Option("local", "--profile")) -> None:
    """Start the user systemd service."""
    profile = _normalize_profile(profile)
    service_name = _service_name(profile)
    _systemctl("start", service_name)
    emit_human(f"started {service_name}")


@app.command("stop")
def stop(profile: str = typer.Option("local", "--profile")) -> None:
    """Stop the user systemd service."""
    profile = _normalize_profile(profile)
    service_name = _service_name(profile)
    _systemctl("stop", service_name)
    emit_human(f"stopped {service_name}")


@app.command("restart")
def restart(profile: str = typer.Option("local", "--profile")) -> None:
    """Restart the user systemd service."""
    profile = _normalize_profile(profile)
    service_name = _service_name(profile)
    _systemctl("restart", service_name)
    emit_human(f"restarted {service_name}")


@app.command("status")
def status(profile: str = typer.Option("local", "--profile")) -> None:
    """Show user systemd service status."""
    profile = _normalize_profile(profile)
    service_name = _service_name(profile)
    result = _systemctl("status", service_name, "--no-pager", check=False)
    body = (result.stdout or result.stderr).strip()
    state = _load_service_state(profile)
    if state and state.public_url:
        body = f"{body}\npublic_url: {state.public_url}"
    emit_human(body)
    raise typer.Exit(code=result.returncode)


@app.command("logs")
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs."),
    lines: int = typer.Option(100, "--lines", min=1, help="Number of log lines to show."),
    profile: str = typer.Option("local", "--profile"),
) -> None:
    """Show journal logs for the user systemd service."""
    profile = _normalize_profile(profile)
    args = [
        "journalctl",
        "--user",
        "-u",
        _service_name(profile),
        "--no-pager",
        "-n",
        str(lines),
    ]
    if follow:
        args.append("-f")
    result = _run(args, check=False)
    emit_human((result.stdout or result.stderr).strip())
    raise typer.Exit(code=result.returncode)
