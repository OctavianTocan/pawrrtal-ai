"""Per-side subprocess orchestration for ``paw mirror``.

Spawns the wrapped paw command twice (local + upstream) in parallel
with isolated config dirs and pre-seeded persona state, then gathers
each side's outcome into a ``SideResult``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.cli.paw.commands.mirror.diff import SideLabel, SideResult, try_parse_json_payload
from app.cli.paw.config import SCHEMA_VERSION, PersonaState

logger = logging.getLogger(__name__)

# Profile + config-dir prefix used per side. Override via ``--persona-prefix``
# if the caller needs to nest a mirror run inside another mirror run.
DEFAULT_PERSONA_PREFIX = "paw-mirror"

# Env vars stripped from each child's environment so a mirror run nested
# inside ``paw record`` (or any other instrumented parent) does not have
# both sides concurrently writing to the same fixture file.
_ENV_VARS_TO_STRIP: tuple[str, ...] = ("PAW_RECORD",)

# Per-side allocation tuple: (label, profile, backend_url, side_dir).
SideAllocation = tuple[SideLabel, str, str, Path]


def allocate_side_dirs(
    parent_config_root: Path,
    prefix: str,
    local_url: str,
    upstream_url: str,
) -> list[SideAllocation]:
    """Reserve the per-side config dir + profile name for both children.

    Each side runs with its own ``PAW_CONFIG_DIR`` so cookies + persona
    state never collide with the parent process or sibling side.
    """
    sides: list[SideAllocation] = []
    label_url_pairs: tuple[tuple[SideLabel, str], ...] = (
        ("local", local_url),
        ("upstream", upstream_url),
    )
    for label, url in label_url_pairs:
        profile = f"{prefix}-{label}"
        side_dir = parent_config_root / f".mirror-{profile}"
        side_dir.mkdir(parents=True, exist_ok=True)
        _seed_side_state(side_dir, profile, url)
        sides.append((label, profile, url, side_dir))
    return sides


def _seed_side_state(side_dir: Path, profile: str, backend_url: str) -> None:
    """Write a minimal ``state.json`` for the side so the child uses ``backend_url``.

    Children read ``api_base_url`` from their persisted ``PersonaState``;
    without seeding, an empty config dir spins up a fresh state pointing
    at the default local backend and the mirror would compare local vs
    local. We write the JSON directly to the per-side directory instead
    of mutating ``PAW_CONFIG_DIR`` and calling ``PersonaState.save``,
    since global env mutation is racy when both sides allocate in
    parallel via tests or future async callers.
    """
    profile_dir = side_dir / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    state = PersonaState(
        profile=profile,
        api_base_url=backend_url,
        created_at=now,
        last_used_at=now,
    )
    state_path = profile_dir / "state.json"
    payload = asdict(state)
    payload["schema_version"] = SCHEMA_VERSION
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    state_path.chmod(0o600)


def cleanup_side_dirs(sides: list[SideAllocation]) -> None:
    """Remove every per-side directory we allocated this run."""
    for _, _, _, side_dir in sides:
        try:
            shutil.rmtree(side_dir, ignore_errors=False)
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Failed to remove mirror side dir", extra={"path": str(side_dir)})


async def run_both_sides(
    wrapped_args: list[str],
    sides: list[SideAllocation],
) -> list[SideResult]:
    """Spawn local + upstream children in parallel and gather their results."""
    tasks = [
        asyncio.create_task(run_side(label, profile, backend_url, side_dir, wrapped_args))
        for label, profile, backend_url, side_dir in sides
    ]
    return await asyncio.gather(*tasks)


async def run_side(
    label: SideLabel,
    profile: str,
    backend_url: str,
    side_dir: Path,
    wrapped_args: list[str],
) -> SideResult:
    """Execute the wrapped paw command in one child subprocess."""
    env = _build_child_env(profile, side_dir, backend_url)
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.cli.paw.main",
        *wrapped_args,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return SideResult(
        label=label,
        backend_url=backend_url,
        profile=profile,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        parsed=try_parse_json_payload(stdout),
    )


def _build_child_env(profile: str, side_dir: Path, backend_url: str) -> dict[str, str]:
    """Compose the env passed to one side's child subprocess.

    - ``PAW_CONFIG_DIR`` isolates cookies + persona state per side.
    - ``PAW_PROFILE`` carries the slot's profile name.
    - ``PAW_BACKEND_URL`` is the whole point of mirror — each side
      points at a different backend so we can diff their responses.
    - ``PAW_RECORD`` is stripped so a mirror nested under ``paw record``
      does not have both sides writing to the same fixture file.
    """
    env = dict(os.environ)
    for var in _ENV_VARS_TO_STRIP:
        env.pop(var, None)
    env["PAW_CONFIG_DIR"] = str(side_dir)
    env["PAW_PROFILE"] = profile
    env["PAW_BACKEND_URL"] = backend_url
    return env
