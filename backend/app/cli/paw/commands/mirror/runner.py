"""Per-side subprocess orchestration for ``paw mirror``.

Spawns the wrapped paw command twice (local + upstream) in parallel
with isolated config dirs and pre-seeded persona state, then gathers
each side's outcome into a ``SideResult``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.cli.paw.commands.child_env import (
    add_provider_credentials,
    build_base_child_env,
    upstream_is_local,
    warn_on_dropped_paw_record,
)
from app.cli.paw.commands.mirror.diff import SideLabel, SideResult, try_parse_json_payload
from app.cli.paw.config import SCHEMA_VERSION, PersonaState

logger = logging.getLogger(__name__)

# Profile + config-dir prefix used per side. Override via ``--persona-prefix``
# if the caller needs to nest a mirror run inside another mirror run.
DEFAULT_PERSONA_PREFIX = "paw-mirror"

# Per-side default wall-clock cap. Mirrors the existing ``--per-slot-timeout``
# semantics on fanout. 600s is generous for chat turns with tool loops but
# tight enough that a hung child gets reaped instead of orphaning the run.
DEFAULT_PER_SIDE_TIMEOUT_S = 600.0

# Graceful-shutdown window after SIGTERM before escalating to SIGKILL when
# tearing down a child on cancel or timeout. Long enough for httpx to flush
# the SSE consumer but short enough that the user's ^C still feels snappy.
CHILD_TERMINATE_GRACE_S = 5.0

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
    *,
    per_side_timeout_s: float = DEFAULT_PER_SIDE_TIMEOUT_S,
) -> list[SideResult]:
    """Spawn local + upstream children in parallel and gather their results."""
    warn_on_dropped_paw_record()
    tasks = [
        asyncio.create_task(
            run_side(
                label,
                profile,
                backend_url,
                side_dir,
                wrapped_args,
                per_side_timeout_s=per_side_timeout_s,
            )
        )
        for label, profile, backend_url, side_dir in sides
    ]
    return await asyncio.gather(*tasks)


async def run_side(
    label: SideLabel,
    profile: str,
    backend_url: str,
    side_dir: Path,
    wrapped_args: list[str],
    *,
    per_side_timeout_s: float = DEFAULT_PER_SIDE_TIMEOUT_S,
) -> SideResult:
    """Execute the wrapped paw command in one child subprocess.

    Wraps ``proc.communicate()`` in try/except so cancellation
    (``KeyboardInterrupt`` from ^C, or an ``asyncio.CancelledError``
    propagated from a sibling task that raised) terminates the child
    instead of leaving it orphaned. A wall-clock cap escalates to
    SIGTERM → SIGKILL the same way; the resulting ``SideResult``
    surfaces ``exit_code = -1`` so the orchestrator's aggregate exit
    still flags the run as failed.
    """
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
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=per_side_timeout_s,
        )
        timed_out = False
    except (asyncio.CancelledError, KeyboardInterrupt):
        await _terminate_child(proc)
        raise
    except TimeoutError:
        logger.warning(
            "Mirror side timed out; terminating child",
            extra={"label": label, "backend_url": backend_url, "timeout_s": per_side_timeout_s},
        )
        await _terminate_child(proc)
        stdout_bytes = b""
        stderr_bytes = f"mirror: side timed out after {per_side_timeout_s}s\n".encode()
        timed_out = True
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    exit_code = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)
    return SideResult(
        label=label,
        backend_url=backend_url,
        profile=profile,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        parsed=try_parse_json_payload(stdout),
    )


async def _terminate_child(proc: asyncio.subprocess.Process) -> None:
    """SIGTERM → SIGKILL escalation for a child being torn down on cancel/timeout.

    Mirrors the dev-backend stop flow so behavior stays consistent
    across orchestrators. SIGTERM gives httpx a chance to flush the
    SSE consumer; SIGKILL is the fallback when the child ignores it.
    """
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=CHILD_TERMINATE_GRACE_S)
        return
    except TimeoutError:
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        return
    await proc.wait()


def _build_child_env(profile: str, side_dir: Path, backend_url: str) -> dict[str, str]:
    """Compose the env passed to one side's child subprocess.

    Built from an allowlist rather than ``dict(os.environ)`` so provider
    secrets cannot leak to an attacker-controlled upstream. Provider
    credentials are forwarded only when the upstream URL parses to a
    loopback host — see :func:`upstream_is_local`.

    - ``PAW_CONFIG_DIR`` isolates cookies + persona state per side.
    - ``PAW_PROFILE`` carries the slot's profile name.
    - ``PAW_BACKEND_URL`` is the whole point of mirror — each side
      points at a different backend so we can diff their responses.
    - ``PAW_RECORD`` is dropped so a mirror nested under ``paw record``
      does not have both sides writing to the same fixture file.
    """
    env = build_base_child_env()
    env["PAW_CONFIG_DIR"] = str(side_dir)
    env["PAW_PROFILE"] = profile
    env["PAW_BACKEND_URL"] = backend_url
    if upstream_is_local(backend_url):
        add_provider_credentials(env)
    return env
