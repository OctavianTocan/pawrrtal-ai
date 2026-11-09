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

# <skill-gen>
# ---
# name: paw-extend
# description: Extend or maintain the paw CLI (backend/app/cli/paw/). Use when adding a new paw subcommand, a new verify suite, a new output mode, an orchestrator command (like fanout/mirror/dev), or refactoring the shared helpers (http.py, sse.py, output.py, errors.py). The user-facing skill is `paw` -- this one teaches you how the surface is built so the next addition fits the existing patterns instead of inventing parallels.
# paths:
#   - "backend/app/cli/paw/**/*.py"
#   - "backend/tests/paw/**/*.py"
#   - "backend/tests/e2e_paw/**/*.py"
#   - ".cursor/plugins/pawrrtal/skills/paw/SKILL.md"
# ---
#
# # paw-extend -- how to add to the paw CLI
#
# The operational skill (`paw`) covers how to use paw. This one covers how to
# build on it. Read both when adding a new command, verify suite, or shared
# helper.
#
# ## File layout
#
# ```text
# backend/app/cli/paw/
# |-- __init__.py              version + public surface
# |-- main.py                  top-level Typer app; every command registers here
# |-- config.py                PersonaState, PAW_CONFIG_DIR, profile resolution
# |-- errors.py                PawError hierarchy -> exit codes
# |-- http.py                  PawClient, cookie jar, record hooks, retry
# |-- ids.py                   new_conversation_id() v4 UUID helper
# |-- output.py                emit_human / emit_json / emit_plain_rows
# |-- sse.py                   byte-level SSE framer + raw-frame tap
# |-- commands/                one file or package per top-level verb/group
# `-- verify/                  one file per verification scenario
# ```
#
# Tests sit at `backend/tests/paw/test_command_<name>.py` (mocked, fast) and
# `backend/tests/e2e_paw/` (live-backend gated on `PAW_E2E=1`).
#
# `PersonaState` is the shared per-profile state. New commands should accept
# `--profile`, load state with `PersonaState.load(profile)`, and respect
# `PAW_BACKEND_URL`/API override behavior instead of inventing a parallel config
# path.
# </skill-gen>


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
    "prod": "https://pawrrtal.octaviantocan.com",
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
            return _apply_backend_override(cls(profile=profile))
        raw = json.loads(p.read_text())
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError(
                f"State schema mismatch at {p}. Run `paw login --force` to recreate.",
            )
        state = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        return _apply_backend_override(state)

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


def _apply_backend_override(state: PersonaState) -> PersonaState:
    """Apply a process-scoped backend override without mutating saved state."""
    backend_url = os.environ.get("PAW_BACKEND_URL", "").strip()
    if backend_url:
        state.api_base_url = backend_url
    return state
