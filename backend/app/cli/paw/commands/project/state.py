"""State and constants for ``paw project`` full-stack lifecycle."""

from __future__ import annotations

import contextlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.cli.paw.config import profile_dir

PROJECT_STATE_SCHEMA_VERSION = 1
DEFAULT_FRONTEND_URL = "http://localhost:53001"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_BOOT_TIMEOUT_S = 45
HEALTH_PROBE_INTERVAL_S = 0.5
HEALTH_PROBE_TIMEOUT_S = 2.0
SERVER_ERROR_STATUS = 500
GRACEFUL_SHUTDOWN_TIMEOUT_S = 30.0
PID_RECYCLE_TOLERANCE_S = 1.0


@dataclass(slots=True)
class ProjectState:
    """Persisted state for the detached full-project dev orchestrator."""

    schema_version: int
    pid: int
    started_at: str
    log_path: str
    frontend_url: str
    backend_url: str
    start_time: float | None = None


def repo_root() -> Path:
    """Return the repository root from this package."""
    return Path(__file__).resolve().parents[6]


def project_state_path(profile: str) -> Path:
    """Return the project lifecycle state path for ``profile``."""
    return profile_dir(profile) / "project.json"


def project_log_path(profile: str) -> Path:
    """Return the combined full-project dev log path for ``profile``."""
    return profile_dir(profile) / "project.log"


def load_state(profile: str) -> ProjectState | None:
    """Read the project state file, or ``None`` when absent/unreadable."""
    path = project_state_path(profile)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    raw_start_time = raw.get("start_time")
    start_time = float(raw_start_time) if raw_start_time is not None else None
    return ProjectState(
        schema_version=int(raw.get("schema_version", PROJECT_STATE_SCHEMA_VERSION)),
        pid=int(raw["pid"]),
        started_at=str(raw["started_at"]),
        log_path=str(raw["log_path"]),
        frontend_url=str(raw["frontend_url"]),
        backend_url=str(raw["backend_url"]),
        start_time=start_time,
    )


def save_state(profile: str, state: ProjectState) -> None:
    """Persist the project state file."""
    path = project_state_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True))


def delete_state(profile: str) -> None:
    """Remove the project state file if it exists."""
    with contextlib.suppress(FileNotFoundError):
        project_state_path(profile).unlink()
