"""XDG config paths + profile resolution + persona state file IO."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.cli.paw.errors import LocalError

DEFAULT_PROFILE = "default"
SCHEMA_VERSION = 1


def config_root() -> Path:
    """Return ~/.config/pawrrtal (or PAW_CONFIG_DIR if set)."""
    if "PAW_CONFIG_DIR" in os.environ:
        return Path(os.environ["PAW_CONFIG_DIR"])
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "pawrrtal"


def profile_dir(profile: str = DEFAULT_PROFILE) -> Path:
    """Return the per-profile config directory under ``config_root()``."""
    return config_root() / profile


def state_path(profile: str = DEFAULT_PROFILE) -> Path:
    """Return the path to ``state.json`` for ``profile``."""
    return profile_dir(profile) / "state.json"


def cookies_path(profile: str = DEFAULT_PROFILE) -> Path:
    """Return the path to ``cookies.txt`` for ``profile``."""
    return profile_dir(profile) / "cookies.txt"


ENV_BASE_URLS = {
    "local": "http://127.0.0.1:8000",
    "dev": "https://dev.pawrrtal.dev",
    "stg": "https://staging.pawrrtal.dev",
    "prod": "https://pawrrtal.com",
}


@dataclass
class PersonaState:
    """Persistent per-profile persona state written to ``state.json``.

    Carries the persona's API base URL, identity, workspace defaults,
    and timestamps. Versioned by :data:`SCHEMA_VERSION`; mismatches
    surface as a "run ``paw login --force``" error rather than silent
    decoding.
    """

    schema_version: int = SCHEMA_VERSION
    profile: str = DEFAULT_PROFILE
    env: str = "local"
    api_base_url: str = ENV_BASE_URLS["local"]
    user_id: str | None = None
    user_email: str | None = None
    default_workspace_id: str | None = None
    default_workspace_path: str | None = None
    default_model_id: str | None = None
    current_conversation_id: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    last_used_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )

    @classmethod
    def load(cls, profile: str = DEFAULT_PROFILE) -> PersonaState:
        """Load the persona state JSON for ``profile`` or return a fresh default."""
        p = state_path(profile)
        if not p.exists():
            return cls(profile=profile)
        raw = json.loads(p.read_text())
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError(
                f"State schema mismatch at {p}. Run `paw login --force` to recreate.",
            )
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})

    def save(self) -> None:
        """Atomically write the state JSON, chmod 0600."""
        self.last_used_at = datetime.now(UTC).isoformat()
        p = state_path(self.profile)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".state.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(asdict(self), f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            Path(tmp).chmod(0o600)
            Path(tmp).replace(p)
        except Exception:
            with contextlib.suppress(OSError):
                Path(tmp).unlink()
            raise


def load_state(profile: str) -> PersonaState:
    """Load persona state for ``profile``; surface a friendly hint when absent.

    Shared wrapper around :meth:`PersonaState.load` that maps a missing
    state file to a ``LocalError`` with a ``paw login`` hint, so every
    command surfaces the same message instead of duplicating the
    try/except boilerplate locally.
    """
    try:
        return PersonaState.load(profile)
    except FileNotFoundError as e:
        raise LocalError(
            f"No persona state for profile {profile!r}.",
            hint="Run `paw login` first.",
        ) from e
