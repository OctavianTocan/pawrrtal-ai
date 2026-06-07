"""Persisted state for Pawrrtal Cloudflared project services."""

from __future__ import annotations

import contextlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.cli.paw.commands.project.state import service_state_path

CLOUDFLARED_PROFILE = "cloudflared"
CLOUDFLARED_STATE_SCHEMA_VERSION = 1


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


def state_path() -> Path:
    """Return the Cloudflared project service state path."""
    return service_state_path(CLOUDFLARED_PROFILE)


def save_state(state: CloudflaredState) -> None:
    """Persist Cloudflared project service state."""
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True))


def load_state() -> CloudflaredState | None:
    """Load Cloudflared deployment state, returning ``None`` when absent."""
    path = state_path()
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


def delete_state() -> None:
    """Delete Cloudflared project service state if it exists."""
    with contextlib.suppress(FileNotFoundError):
        state_path().unlink()
