"""Persisted dev-backend state — JSON at ``<PAW_CONFIG_DIR>/<profile>/dev.json``.

Owns the on-disk record that ``paw dev up`` writes and ``paw dev down``
/ ``paw dev status`` read. Kept separate from process orchestration so
the state schema can evolve independently of the spawn / signal logic.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from app.cli.paw.config import profile_dir

logger = logging.getLogger(__name__)

# State file schema version. Bump when the persisted shape changes.
DEV_STATE_SCHEMA_VERSION = 2


@dataclass(slots=True)
class DevState:
    """Persisted record of the running dev backend.

    Stored as JSON at ``<PAW_CONFIG_DIR>/<profile>/dev.json``.

    ``start_time`` is the OS-reported process creation time (seconds
    since epoch), captured at spawn. It exists for one reason: PID
    recycling. The kernel reuses PIDs aggressively, so between the
    ``paw dev up`` write and a later ``paw dev down`` read, the original
    process may have died and an unrelated process picked up the same
    PID. ``stop_tracked_backend`` re-reads the live process's creation
    time and refuses to signal if it doesn't match what we persisted.
    Stored as ``float | None`` so a missing value forces the conservative
    refuse-to-signal path.
    """

    schema_version: int
    pid: int
    host: str
    port: int
    started_at: str
    log_path: str
    start_time: float | None = None


def dev_state_path(profile: str) -> Path:
    """Return the dev state file path for ``profile``."""
    return profile_dir(profile) / "dev.json"


def dev_log_path(profile: str) -> Path:
    """Return the dev backend log file path for ``profile``."""
    return profile_dir(profile) / "dev.log"


def load_state(profile: str) -> DevState | None:
    """Read the persisted state file, or ``None`` if absent / unreadable."""
    path = dev_state_path(profile)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to read dev state file; treating as absent",
            extra={"path": str(path), "error": str(exc)},
        )
        return None
    raw_start_time = raw.get("start_time")
    start_time = float(raw_start_time) if raw_start_time is not None else None
    return DevState(
        schema_version=int(raw.get("schema_version", DEV_STATE_SCHEMA_VERSION)),
        pid=int(raw["pid"]),
        host=str(raw["host"]),
        port=int(raw["port"]),
        started_at=str(raw["started_at"]),
        log_path=str(raw["log_path"]),
        start_time=start_time,
    )


def save_state(profile: str, state: DevState) -> None:
    """Persist the dev state file atomically."""
    path = dev_state_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True))


def delete_state(profile: str) -> None:
    """Remove the dev state file if it exists. Idempotent."""
    path = dev_state_path(profile)
    try:
        path.unlink()
    except FileNotFoundError:
        return
