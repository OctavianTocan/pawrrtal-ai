"""Cloudflared named-tunnel operations for the Pawrrtal project."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import typer

from app.cli.paw.commands.project.state import (
    DEFAULT_BACKEND_URL,
    HEALTH_PROBE_TIMEOUT_S,
    SERVER_ERROR_STATUS,
    service_state_path,
)
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

app = typer.Typer(no_args_is_help=True)

CLOUDFLARED_PROFILE = "cloudflared"
CLOUDFLARED_SERVICE = "cloudflared"
DEFAULT_TUNNEL_NAME = "pawrrtal"
DEFAULT_CONFIG_PATH = Path("/etc/cloudflared/config.yml")
DEFAULT_METRICS_ADDRESS = "127.0.0.1:20241"
DEFAULT_TUNNEL_FRONTEND_ORIGIN = "http://127.0.0.1:3000"
CLOUDFLARED_STATE_SCHEMA_VERSION = 1
HOSTNAME_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
SENSITIVE_OUTPUT_MARKERS = ("token", "secret", "origin cert", "cert.pem", "tunnel credentials")
MAX_SAFE_OUTPUT_LINES = 3


@dataclass(slots=True)
class CloudflaredState:
    """Persisted state for the Pawrrtal Cloudflared tunnel."""

    schema_version: int
    tunnel_name: str
    tunnel_id: str
    hostname: str
    public_url: str
    config_path: str
    credentials_file: str
    frontend_origin: str
    backend_origin: str
    metrics: str
    installed_at: str


@dataclass(slots=True)
class PublicAccessProbe:
    """Public hostname response used to decide whether Access is in front."""

    url: str
    status_code: int
    location: str
    access_required: bool


def _state_path() -> Path:
    return service_state_path(CLOUDFLARED_PROFILE)


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=check, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise LocalError(f"`{args[0]}` not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        hint = _safe_command_output(exc.stderr or exc.stdout or "")
        raise LocalError(
            f"`{' '.join(args)}` failed with exit code {exc.returncode}.",
            hint=hint,
        ) from exc


def _cloudflared(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["cloudflared", *args], check=check)


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["systemctl", *args], check=check)


def _safe_command_output(text: str) -> str | None:
    lines = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in SENSITIVE_OUTPUT_MARKERS):
            continue
        lines.append(line)
        if len(lines) == MAX_SAFE_OUTPUT_LINES:
            break
    return "\n".join(lines) or None


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise LocalError(f"`{name}` not found on PATH.", hint=f"Install {name}, then retry.")
    return path


def _normalize_hostname(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise LocalError("--hostname is required.")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.path not in ("", "/"):
        raise LocalError("--hostname must not include a path.")
    if parsed.port is not None:
        raise LocalError("--hostname must not include a port.")
    hostname = (parsed.hostname or "").lower()
    if not HOSTNAME_RE.fullmatch(hostname):
        raise LocalError(f"Invalid hostname: {value}")
    return hostname


def _assert_loopback_origin(origin: str, *, label: str) -> None:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        raise LocalError(f"{label} origin must use http or https.")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise LocalError(f"{label} origin must be loopback-only.")
    if parsed.path not in ("", "/"):
        raise LocalError(f"{label} origin must not include a path.")


def _origin_health_url(origin: str, *, backend: bool) -> str:
    base = origin.rstrip("/")
    if backend:
        return f"{base}/api/v1/health"
    return f"{base}/"


def _probe_origin(origin: str, *, backend: bool) -> bool:
    url = _origin_health_url(origin, backend=backend)
    try:
        response = httpx.get(url, timeout=HEALTH_PROBE_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return response.status_code < SERVER_ERROR_STATUS


def _validate_origins(frontend_origin: str, backend_origin: str) -> None:
    _assert_loopback_origin(frontend_origin, label="Frontend")
    _assert_loopback_origin(backend_origin, label="Backend")
    if not _probe_origin(frontend_origin, backend=False):
        raise LocalError(f"Frontend origin is not reachable: {frontend_origin}")
    if not _probe_origin(backend_origin, backend=True):
        raise LocalError(f"Backend origin is not reachable: {backend_origin}")


def _render_config(
    *,
    tunnel_id: str,
    credentials_file: Path,
    hostname: str,
    frontend_origin: str,
    backend_origin: str,
    metrics: str,
) -> str:
    """Render the Cloudflared ingress config for Pawrrtal."""
    return "\n".join(
        [
            f"tunnel: {tunnel_id}",
            f"credentials-file: {credentials_file}",
            f"metrics: {metrics}",
            "",
            "ingress:",
            f"  - hostname: {hostname}",
            "    path: ^/api/v1/.*",
            f"    service: {backend_origin}",
            f"  - hostname: {hostname}",
            "    path: ^/auth/.*",
            f"    service: {backend_origin}",
            f"  - hostname: {hostname}",
            "    path: ^/users/.*",
            f"    service: {backend_origin}",
            f"  - hostname: {hostname}",
            f"    service: {frontend_origin}",
            "  - service: http_status:404",
            "",
        ]
    )


def _load_tunnels() -> list[dict[str, object]]:
    result = _cloudflared("tunnel", "list", "--output", "json")
    try:
        raw = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise LocalError("Cloudflared returned invalid tunnel list JSON.") from exc
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    tunnels = raw.get("tunnels") if isinstance(raw, dict) else None
    if isinstance(tunnels, list):
        return [item for item in tunnels if isinstance(item, dict)]
    raise LocalError("Cloudflared tunnel list JSON had an unexpected shape.")


def _find_tunnel_id(tunnels: list[dict[str, object]], tunnel_name: str) -> str | None:
    for tunnel in tunnels:
        if tunnel.get("name") != tunnel_name:
            continue
        tunnel_id = tunnel.get("id") or tunnel.get("uuid")
        return str(tunnel_id) if tunnel_id else None
    return None


def _ensure_tunnel(tunnel_name: str) -> str:
    tunnel_id = _find_tunnel_id(_load_tunnels(), tunnel_name)
    if tunnel_id is not None:
        return tunnel_id
    _cloudflared("tunnel", "create", tunnel_name)
    tunnel_id = _find_tunnel_id(_load_tunnels(), tunnel_name)
    if tunnel_id is None:
        raise LocalError(f"Cloudflared did not report a tunnel id for {tunnel_name}.")
    return tunnel_id


def _copy_credentials(*, tunnel_id: str, config_path: Path) -> Path:
    source = Path.home() / ".cloudflared" / f"{tunnel_id}.json"
    if not source.exists():
        raise LocalError(
            f"Cloudflared credentials file is missing for tunnel {tunnel_id}.",
            hint="Run `cloudflared tunnel login`, then retry.",
        )
    target = config_path.parent / f"{tunnel_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o600)
    return target


def _write_config(config_path: Path, config_text: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    config_path.chmod(0o644)


def _validate_ingress(config_path: Path) -> None:
    _cloudflared("--config", str(config_path), "tunnel", "ingress", "validate")


def _install_service(config_path: Path) -> None:
    _cloudflared("--config", str(config_path), "service", "install")
    _systemctl("enable", "--now", CLOUDFLARED_SERVICE)


def _save_state(state: CloudflaredState) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True))


def _load_state() -> CloudflaredState | None:
    """Load Cloudflared deployment state, returning ``None`` when absent."""
    path = _state_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return CloudflaredState(
        schema_version=int(raw.get("schema_version", CLOUDFLARED_STATE_SCHEMA_VERSION)),
        tunnel_name=str(raw["tunnel_name"]),
        tunnel_id=str(raw["tunnel_id"]),
        hostname=str(raw["hostname"]),
        public_url=str(raw["public_url"]),
        config_path=str(raw["config_path"]),
        credentials_file=str(raw["credentials_file"]),
        frontend_origin=str(raw["frontend_origin"]),
        backend_origin=str(raw["backend_origin"]),
        metrics=str(raw["metrics"]),
        installed_at=str(raw["installed_at"]),
    )


def _delete_state() -> None:
    with contextlib.suppress(FileNotFoundError):
        _state_path().unlink()


def _public_access_probe(hostname: str) -> PublicAccessProbe:
    url = f"https://{hostname}/"
    try:
        response = httpx.get(url, follow_redirects=False, timeout=HEALTH_PROBE_TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise LocalError(f"Public hostname is not reachable: {url}") from exc
    location = response.headers.get("location", "")
    return PublicAccessProbe(
        url=url,
        status_code=response.status_code,
        location=location,
        access_required=_looks_like_access(response.status_code, response.headers),
    )


def _looks_like_access(status_code: int, headers: httpx.Headers) -> bool:
    location = headers.get("location", "").lower()
    if "/cdn-cgi/access" in location or "cloudflareaccess.com" in location:
        return True
    if headers.get("cf-access-domain") or headers.get("cf-access-auth-domain"):
        return True
    return status_code in {401, 403}


def _service_state() -> tuple[str, str]:
    active = _systemctl("is-active", CLOUDFLARED_SERVICE, check=False)
    enabled = _systemctl("is-enabled", CLOUDFLARED_SERVICE, check=False)
    return (active.stdout or active.stderr).strip(), (enabled.stdout or enabled.stderr).strip()


def _resolve_status_config_path(
    *,
    requested_config_path: Path | None,
    state: CloudflaredState | None,
) -> Path:
    """Return the config path that status should inspect."""
    if requested_config_path is not None:
        return requested_config_path
    if state is not None:
        return Path(state.config_path)
    return DEFAULT_CONFIG_PATH


def _path_exists(path: Path) -> bool:
    """Return whether a path exists without exposing filesystem permission errors."""
    try:
        return path.exists()
    except OSError:
        return False


def _status_payload(config_path: Path | None) -> dict[str, object]:
    state = _load_state()
    resolved_config_path = _resolve_status_config_path(
        requested_config_path=config_path,
        state=state,
    )
    active, enabled = _service_state()
    version = _cloudflared("--version", check=False)
    return {
        "installed": state is not None,
        "service_active": active,
        "service_enabled": enabled,
        "cloudflared_version": (version.stdout or version.stderr).strip(),
        "config_path": str(resolved_config_path),
        "config_exists": _path_exists(resolved_config_path),
        "hostname": state.hostname if state else None,
        "public_url": state.public_url if state else None,
        "tunnel_name": state.tunnel_name if state else None,
        "metrics": state.metrics if state else DEFAULT_METRICS_ADDRESS,
    }


def _emit_status(payload: dict[str, object], *, json_out: bool, plain: bool) -> None:
    """Emit Cloudflared status in the selected output mode."""
    if json_out:
        emit_json(payload)
        return
    if plain:
        emit_plain_rows([[payload["tunnel_name"], payload["hostname"], payload["service_active"]]])
        return
    emit_human(
        "\n".join(
            [
                f"installed: {payload['installed']}",
                f"service: {payload['service_active']} ({payload['service_enabled']})",
                f"hostname: {payload.get('hostname') or ''}",
                f"config: {payload['config_path']}",
                f"metrics: {payload['metrics']}",
            ]
        )
    )


@app.command("install")
def install(
    hostname: str = typer.Option(..., "--hostname", help="Public hostname to route."),
    tunnel_name: str = typer.Option(
        DEFAULT_TUNNEL_NAME,
        "--tunnel-name",
        help="Cloudflared named tunnel.",
    ),
    config_path: Path = typer.Option(
        DEFAULT_CONFIG_PATH,
        "--config-path",
        help="Cloudflared config path.",
    ),
    frontend_origin: str = typer.Option(
        DEFAULT_TUNNEL_FRONTEND_ORIGIN,
        "--frontend-origin",
        help="Loopback frontend origin.",
    ),
    backend_origin: str = typer.Option(
        DEFAULT_BACKEND_URL,
        "--backend-origin",
        help="Loopback backend origin.",
    ),
) -> None:
    """Install the Pawrrtal Cloudflared tunnel service."""
    host = _normalize_hostname(hostname)
    _require_binary("cloudflared")
    _validate_origins(frontend_origin, backend_origin)
    tunnel_id = _ensure_tunnel(tunnel_name)
    credentials_file = _copy_credentials(tunnel_id=tunnel_id, config_path=config_path)
    config_text = _render_config(
        tunnel_id=tunnel_id,
        credentials_file=credentials_file,
        hostname=host,
        frontend_origin=frontend_origin,
        backend_origin=backend_origin,
        metrics=DEFAULT_METRICS_ADDRESS,
    )
    _write_config(config_path, config_text)
    _validate_ingress(config_path)
    _cloudflared("tunnel", "route", "dns", tunnel_name, host)
    _install_service(config_path)
    _save_state(
        CloudflaredState(
            schema_version=CLOUDFLARED_STATE_SCHEMA_VERSION,
            tunnel_name=tunnel_name,
            tunnel_id=tunnel_id,
            hostname=host,
            public_url=f"https://{host}/",
            config_path=str(config_path),
            credentials_file=str(credentials_file),
            frontend_origin=frontend_origin,
            backend_origin=backend_origin,
            metrics=DEFAULT_METRICS_ADDRESS,
            installed_at=datetime.now(UTC).isoformat(),
        )
    )
    emit_human(
        "\n".join(
            [
                f"installed Cloudflared tunnel {tunnel_name} for https://{host}/",
                f"config: {config_path}",
                "access: require Cloudflare Access before opening the app.",
            ]
        )
    )


@app.command("verify")
def verify(
    hostname: str | None = typer.Option(None, "--hostname", help="Public hostname to verify."),
    tunnel_name: str = typer.Option(DEFAULT_TUNNEL_NAME, "--tunnel-name"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
    frontend_origin: str = typer.Option(DEFAULT_TUNNEL_FRONTEND_ORIGIN, "--frontend-origin"),
    backend_origin: str = typer.Option(DEFAULT_BACKEND_URL, "--backend-origin"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Verify local origins, Cloudflared config, service state, and Access."""
    state = _load_state()
    host = _normalize_hostname(hostname or (state.hostname if state else ""))
    _require_binary("cloudflared")
    _validate_origins(frontend_origin, backend_origin)
    _validate_ingress(config_path)
    _cloudflared("tunnel", "info", tunnel_name)
    active, enabled = _service_state()
    public_probe = _public_access_probe(host)
    if not public_probe.access_required:
        raise LocalError(
            f"Cloudflare Access is not protecting https://{host}/.",
            hint="Expected an Access challenge or deny response, not direct app HTML.",
        )
    payload = {
        "ok": True,
        "hostname": host,
        "tunnel_name": tunnel_name,
        "config_path": str(config_path),
        "service_active": active,
        "service_enabled": enabled,
        "access_required": True,
        "public_status": public_probe.status_code,
        "public_location": public_probe.location,
    }
    if json_out:
        emit_json(payload)
        return
    emit_human(f"cloudflared ok: https://{host}/ is protected by Cloudflare Access")


@app.command("status")
def status(
    config_path: Path | None = typer.Option(None, "--config-path"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
    plain: bool = typer.Option(False, "--plain", help="TSV: tunnel hostname service."),
) -> None:
    """Show Cloudflared tunnel and service status."""
    require_one_output_mode(json_out=json_out, plain=plain)
    _require_binary("cloudflared")
    _emit_status(_status_payload(config_path), json_out=json_out, plain=plain)


@app.command("uninstall")
def uninstall(
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config-path"),
    keep_config: bool = typer.Option(False, "--keep-config", help="Leave config and credentials."),
) -> None:
    """Disable Cloudflared and remove Pawrrtal-managed files."""
    state = _load_state()
    _systemctl("disable", "--now", CLOUDFLARED_SERVICE, check=False)
    _cloudflared("service", "uninstall", check=False)
    if not keep_config:
        config_path.unlink(missing_ok=True)
        if state is not None:
            Path(state.credentials_file).unlink(missing_ok=True)
    _delete_state()
    emit_human("removed Cloudflared Pawrrtal service")
