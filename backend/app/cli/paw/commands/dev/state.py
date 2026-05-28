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

# State file schema version. Bump when the persisted shape changes
# in a non-backwards-compatible way.
DEV_STATE_SCHEMA_VERSION = 1


@dataclass(slots=True)
class DevState:
    """Persisted record of the running dev backend.

    Stored as JSON at ``<PAW_CONFIG_DIR>/<profile>/dev.json``.
    """

    schema_version: int
    pid: int
    host: str
    port: int
    started_at: str
    log_path: str


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
    return DevState(
        schema_version=int(raw.get("schema_version", DEV_STATE_SCHEMA_VERSION)),
        pid=int(raw["pid"]),
        host=str(raw["host"]),
        port=int(raw["port"]),
        started_at=str(raw["started_at"]),
        log_path=str(raw["log_path"]),
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
