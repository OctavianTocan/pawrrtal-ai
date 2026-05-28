"""paw fanout — spawn N parallel personas against the same backend.

`fanout` is a local CLI orchestrator, not a backend feature. It re-invokes
``paw`` N times in parallel as subprocesses, each with an isolated config
directory (``PAW_CONFIG_DIR``) and a distinct profile name
(``PAW_PROFILE``), so cookies and persona state cannot collide. Outputs
are aggregated into one human table or a JSON array per slot. Useful for
stress-testing chat-flow concurrency and the live E2E suite.

Example::

    paw fanout 5 conversations send "hello" --new --model litellm:openai/gpt-4o-mini
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import typer

from app.cli.paw.config import config_root
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json

logger = logging.getLogger(__name__)

# Default prefix used to name the per-slot profile + config-dir slot. Override
# via ``--persona-prefix`` to avoid collisions when nesting fanout runs.
DEFAULT_PERSONA_PREFIX = "paw-fanout"

# Cap for slot count so a typo (`paw fanout 1000000 ...`) cannot fork-bomb the
# host. The real workload caps are concurrency + backend rate limits; this is
# just a guardrail.
MAX_SLOTS = 256

# Truncate captured child stdout/stderr in the human renderer so a chatty
# child does not flood the terminal. The JSON output preserves the full
# capture.
HUMAN_OUTPUT_PREVIEW_BYTES = 256


@dataclass(slots=True)
class SlotResult:
    """One child's outcome. ``duration_ms`` is wall-clock for the subprocess."""

    slot: int
    profile: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


def fanout(
    ctx: typer.Context,
    n: int = typer.Argument(..., help="Number of parallel personas to spawn."),
    max_concurrent: int = typer.Option(
        0,
        "--max-concurrent",
        help="Cap simultaneous children. 0 (default) = no cap, run all at once.",
        min=0,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON array of per-slot results instead of the human table.",
    ),
    persona_prefix: str = typer.Option(
        DEFAULT_PERSONA_PREFIX,
        "--persona-prefix",
        help="Profile/config-dir slot prefix; each slot becomes `<prefix>-<i>`.",
    ),
    keep_personas: bool = typer.Option(
        False,
        "--keep-personas",
        help="Do not delete per-slot persona config dirs after the run.",
    ),
) -> None:
    """Spawn ``n`` parallel personas and run the wrapped paw command in each.

    Examples:
      paw fanout 5 conversations send "hello" --new --model litellm:openai/gpt-4o-mini
      paw fanout 3 --json auth status
      paw fanout 10 --max-concurrent 3 verify chat-roundtrip --json
    """
    extra = list(ctx.args)
    if not extra:
        raise LocalError(
            "Missing command to fan out. Example: paw fanout 5 auth status",
            hint="Append the paw subcommand after the slot count.",
        )
    if n <= 0:
        raise LocalError(
            f"Slot count must be >= 1 (got {n}).",
            hint="Pass a positive integer before the wrapped command.",
        )
    if n > MAX_SLOTS:
        raise LocalError(
            f"Slot count {n} exceeds the safety cap of {MAX_SLOTS}.",
            hint=f"Raise MAX_SLOTS in fanout.py if you genuinely need more than {MAX_SLOTS}.",
        )

    parent_config_root = config_root()
    slot_dirs = _allocate_slot_dirs(parent_config_root, persona_prefix, n)
    concurrency = n if max_concurrent == 0 else max_concurrent
    try:
        results = asyncio.run(
            _run_all(extra, slot_dirs, persona_prefix, concurrency),
        )
    finally:
        if not keep_personas:
            _cleanup_slot_dirs(slot_dirs)

    if json_output:
        emit_json([_serialise_result(r) for r in results])
    else:
        _emit_human_summary(results)

    aggregate = max((r.exit_code for r in results), default=0)
    if aggregate != 0:
        raise typer.Exit(code=aggregate)


def _allocate_slot_dirs(
    parent_config_root: Path,
    prefix: str,
    n: int,
) -> list[tuple[int, str, Path]]:
    """Reserve ``n`` per-slot config directories.

    Each child runs with its own ``PAW_CONFIG_DIR`` so cookies and persona
    state never collide. Directories live under the parent's config root so
    they're visible to ``paw doctor`` if cleanup is skipped.
    """
    slots: list[tuple[int, str, Path]] = []
    for i in range(n):
        profile = f"{prefix}-{i}"
        slot_dir = parent_config_root / f".fanout-{profile}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        slots.append((i, profile, slot_dir))
    return slots


def _cleanup_slot_dirs(slot_dirs: list[tuple[int, str, Path]]) -> None:
    """Remove every per-slot directory we allocated this run.

    Conservative: only deletes dirs we just created (their paths are
    returned by ``_allocate_slot_dirs``); never touches user data.
    """
    for _, _, slot_dir in slot_dirs:
        try:
            shutil.rmtree(slot_dir, ignore_errors=False)
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Failed to remove fanout slot dir", extra={"path": str(slot_dir)})


async def _run_all(
    wrapped_args: list[str],
    slot_dirs: list[tuple[int, str, Path]],
    prefix: str,
    concurrency: int,
) -> list[SlotResult]:
    """Spawn every slot subject to a concurrency semaphore.

    Returns slots in original order so ``[slot 0]`` is always first in the
    rendered output.
    """
    sem = asyncio.Semaphore(max(1, concurrency))
    _ = prefix
    tasks = [
        asyncio.create_task(_run_slot(slot, profile, slot_dir, wrapped_args, sem))
        for slot, profile, slot_dir in slot_dirs
    ]
    return await asyncio.gather(*tasks)


async def _run_slot(
    slot: int,
    profile: str,
    slot_dir: Path,
    wrapped_args: list[str],
    sem: asyncio.Semaphore,
) -> SlotResult:
    """Execute the wrapped paw command in one child subprocess."""
    async with sem:
        env = _build_child_env(profile, slot_dir)
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
        return SlotResult(
            slot=slot,
            profile=profile,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            duration_ms=duration_ms,
        )


def _build_child_env(profile: str, slot_dir: Path) -> dict[str, str]:
    """Compose the env passed to one child subprocess.

    - ``PAW_CONFIG_DIR`` points at this slot's isolated config directory so
      cookies + persona state never collide with sibling slots or the
      parent process.
    - ``PAW_PROFILE`` carries the slot's profile name. The current CLI
      consumes ``--profile`` per-command, but ``PAW_PROFILE`` is set for
      tools that read it directly and for future env-driven profile
      resolution.
    """
    env = dict(os.environ)
    env["PAW_CONFIG_DIR"] = str(slot_dir)
    env["PAW_PROFILE"] = profile
    return env


def _serialise_result(result: SlotResult) -> dict[str, object]:
    """Stable JSON shape consumed by tests and downstream tooling."""
    return {
        "slot": result.slot,
        "profile": result.profile,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
    }


def _emit_human_summary(results: list[SlotResult]) -> None:
    """Print one row per slot plus an aggregate footer."""
    for result in results:
        emit_human(_format_human_row(result))
    failures = sum(1 for r in results if r.exit_code != 0)
    emit_human(
        f"\nfanout: {len(results)} slot(s), {failures} failure(s), "
        f"aggregate_exit={max((r.exit_code for r in results), default=0)}",
    )


def _format_human_row(result: SlotResult) -> str:
    """Render a single slot's outcome on one line.

    Stdout/stderr are previewed (not full-dumped) so a chatty child does
    not flood the terminal — use ``--json`` for full capture.
    """
    stdout_preview = _summarise_capture(result.stdout)
    stderr_preview = _summarise_capture(result.stderr)
    return (
        f"[slot {result.slot:>3}] profile={result.profile} "
        f"exit={result.exit_code} duration={result.duration_ms}ms "
        f"stdout={stdout_preview} stderr={stderr_preview}"
    )


def _summarise_capture(text: str) -> str:
    """Return ``"<size>B"`` plus the first line, capped at the preview budget."""
    encoded = text.encode("utf-8", errors="replace")
    if not encoded:
        return "0B"
    first_line = text.splitlines()[0] if text else ""
    if len(first_line) > HUMAN_OUTPUT_PREVIEW_BYTES:
        first_line = first_line[:HUMAN_OUTPUT_PREVIEW_BYTES] + "…"
    return f"{len(encoded)}B ({first_line!r})"
