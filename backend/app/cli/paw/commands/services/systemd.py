"""Systemd unit rendering and management for ``paw services``."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.cli.paw.commands.services.targets import (
    CONFIG_PATH_ENV,
    DEFAULT_BWS_ENV_FILE,
    ServiceTarget,
    config_path,
)
from app.cli.paw.errors import LocalError

STANDARD_SERVICE_PATHS = (
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)


def unit_dir() -> Path:
    """Return the systemd unit directory."""
    override = os.environ.get("PAWRRTAL_SYSTEMD_UNIT_DIR")
    return Path(override) if override else Path("/etc/systemd/system")


def unit_path(target: ServiceTarget) -> Path:
    """Return the generated unit path for a target."""
    return unit_dir() / target.service_name


def render_unit(target: ServiceTarget) -> str:
    """Render a systemd unit for a service target."""
    bun = require_binary("bun")
    uv = require_binary("uv")
    node = require_binary("node")
    cache_root = target.workdir / ".cache"
    env_lines = [
        systemd_env_line("PATH", service_path([bun, uv, node])),
        systemd_env_line("UV_CACHE_DIR", str(cache_root / "uv")),
        systemd_env_line("XDG_CACHE_HOME", str(cache_root / "xdg")),
        systemd_env_line("UV_LINK_MODE", "copy"),
        systemd_env_line("NODE_ENV", "production"),
        systemd_env_line("NEXT_TELEMETRY_DISABLED", "1"),
        systemd_env_line("ENV", target.env),
        systemd_env_line("HOSTNAME", "127.0.0.1"),
        systemd_env_line("PORT", str(target.frontend_port)),
        systemd_env_line("PAWRRTAL_BACKEND_HOST", "127.0.0.1"),
        systemd_env_line("PAWRRTAL_BACKEND_PORT", str(target.backend_port)),
        systemd_env_line("BACKEND_INTERNAL_URL", f"http://127.0.0.1:{target.backend_port}"),
        systemd_env_line(CONFIG_PATH_ENV, str(config_path())),
        systemd_env_line("PAWRRTAL_SERVICE_TARGET", target.name),
    ]
    if target.public_hostname:
        env_lines.append(systemd_env_line("PAWRRTAL_PUBLIC_HOSTNAME", target.public_hostname))
    if target.enable_dev_login:
        env_lines.append(systemd_env_line("PAWRRTAL_ENABLE_DEV_LOGIN", "true"))
    env_lines.extend(
        systemd_env_line(key, value) for key, value in sorted(target.environment.items())
    )
    return "\n".join(
        [
            "[Unit]",
            f"Description=Pawrrtal app server ({target.name})",
            "After=network-online.target",
            "Wants=network-online.target",
            "StartLimitIntervalSec=120",
            "StartLimitBurst=3",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={target.workdir}",
            f"EnvironmentFile=-{DEFAULT_BWS_ENV_FILE}",
            *env_lines,
            (
                f"ExecStart={uv} run --project backend python -m "
                f"app.cli.paw.commands.services.launch --target {target.name}"
            ),
            "Restart=on-failure",
            "RestartSec=15",
            "KillMode=control-group",
            "TimeoutStopSec=25",
            "SuccessExitStatus=143 130",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def require_binary(name: str) -> str:
    """Return an absolute binary path or raise an actionable local error."""
    path = shutil.which(name)
    if path is None:
        raise LocalError(f"`{name}` not found on PATH.", hint=f"Install {name}, then retry.")
    return path


def systemd_env_line(name: str, value: str) -> str:
    """Return one quoted systemd Environment= line."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'Environment="{name}={escaped}"'


def service_path(binary_paths: list[str]) -> str:
    """Return a stable PATH for the systemd service."""
    entries = [str(Path(binary_path).parent) for binary_path in binary_paths]
    entries.extend(STANDARD_SERVICE_PATHS)
    return ":".join(dict.fromkeys(entries))


def preflight_systemd() -> None:
    """Fail before writing unit files when systemd is unavailable."""
    result = systemctl("is-system-running", check=False)
    output = (result.stdout or result.stderr or "").strip()
    if "Failed to connect to bus" in output or "Operation not permitted" in output:
        raise LocalError(
            "Systemd is not available in this environment.",
            hint=output or "Run on the deployment host with systemd available.",
        )


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run systemctl with args."""
    return run(["systemctl", *args], check=check)


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
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
