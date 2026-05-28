r"""paw mirror — run a wrapped paw command against local and a remote backend, diff the result.

``mirror`` is a local orchestrator that spawns the wrapped paw command
twice in parallel: once against the local backend (or the value of
``PAW_BACKEND_URL`` in the parent env), once against the URL passed via
``--upstream``. The two children run with isolated config directories and
profiles so cookies + persona state never collide. After both finish, we
diff their outputs to surface provider drift between environments.

Diff algorithm:

- If both children's stdout parses as JSON with the ``conversations send``
  shape (``events`` dict + ``final_text``), we run a *semantic* diff:
  per-event-type count delta (ignoring ``--ignore`` types), ``final_text``
  equality, and — if ``--strict-timing`` is set — a duration delta check.
- Otherwise we fall back to *literal* equality on stdout + exit code.

Exit code semantics (specific to ``mirror``):

- ``0`` — both children succeeded AND no drift detected.
- ``5`` — both children succeeded but the diff found drift (semantic
  mismatch or stdout inequality).
- ``6`` — one or both children exited non-zero (orchestration failure).

Example::

    paw mirror --upstream https://dev.pawrrtal.dev \\
        conversations send "hello" --new \\
        --model litellm:openai/gpt-4o-mini
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import typer

from app.cli.paw.config import PersonaState, config_root
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json

logger = logging.getLogger(__name__)

# Default local backend URL when the parent process has no PAW_BACKEND_URL
# set. Matches ``ENV_BASE_URLS["local"]`` in ``config.py`` so the help and
# behaviour stay aligned with the rest of the CLI.
DEFAULT_LOCAL_BACKEND_URL = "http://127.0.0.1:8000"

# Profile + config-dir prefix used per side. Override via ``--persona-prefix``
# if the caller needs to nest a mirror run inside another mirror run.
DEFAULT_PERSONA_PREFIX = "paw-mirror"

# Event types excluded from the semantic diff by default. ``usage`` is the
# canonical noisy event — token counts almost always differ across
# environments and are not actionable drift.
DEFAULT_IGNORED_EVENT_TYPES: tuple[str, ...] = ("usage",)

# Default threshold (ms) above which ``--strict-timing`` flags a duration
# delta as drift. Picked to be wider than typical p50 noise but narrow
# enough to catch a real provider regression.
DEFAULT_STRICT_TIMING_THRESHOLD_MS = 1000

# Mirror-specific exit codes. ``0`` and ``1`` are inherited from the
# generic CLI conventions (see ``errors.py``); the two below are
# mirror-only.
MIRROR_EXIT_SUCCESS = 0
MIRROR_EXIT_DRIFT = 5
MIRROR_EXIT_CHILD_FAILED = 6

# Stream label used in JSON output keys and human-mode log lines.
SideLabel = Literal["local", "upstream"]


@dataclass(slots=True)
class SideResult:
    """One side's outcome: child subprocess result + parsed payload."""

    label: SideLabel
    backend_url: str
    profile: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    parsed: dict[str, Any] | None


@dataclass(slots=True)
class DiffOutcome:
    """Result of comparing two ``SideResult``s.

    ``has_drift`` is the boolean that drives the exit code. ``mode``
    records which diff algorithm ran ("semantic" or "literal"), and
    ``details`` is the human-readable / JSON-serialisable per-field
    breakdown.
    """

    has_drift: bool
    mode: Literal["semantic", "literal"]
    details: dict[str, Any]


def mirror(
    ctx: typer.Context,
    upstream: str = typer.Option(
        ...,
        "--upstream",
        help="Remote backend URL to mirror against (required).",
    ),
    local: str | None = typer.Option(
        None,
        "--local",
        help=(
            "Local backend URL. Defaults to the parent PAW_BACKEND_URL env "
            f"var, or {DEFAULT_LOCAL_BACKEND_URL} if unset."
        ),
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON diff result instead of the human summary.",
    ),
    strict_timing: bool = typer.Option(
        False,
        "--strict-timing",
        help=(
            "Also flag duration deltas greater than "
            f"{DEFAULT_STRICT_TIMING_THRESHOLD_MS}ms as drift."
        ),
    ),
    ignore: list[str] = typer.Option(
        [],
        "--ignore",
        help=(
            "Event type to exclude from the semantic diff. Repeatable. "
            f"Defaults already exclude: {', '.join(DEFAULT_IGNORED_EVENT_TYPES)}."
        ),
    ),
    persona_prefix: str = typer.Option(
        DEFAULT_PERSONA_PREFIX,
        "--persona-prefix",
        help="Profile/config-dir prefix; each side becomes `<prefix>-<side>`.",
    ),
    keep_personas: bool = typer.Option(
        False,
        "--keep-personas",
        help="Do not delete per-side persona config dirs after the run.",
    ),
) -> None:
    r"""Run the wrapped paw command against local + upstream, diff the result.

    Examples:
      paw mirror --upstream https://dev.pawrrtal.dev conversations send "hello" --new
      paw mirror --upstream https://dev.pawrrtal.dev auth status --json
      paw mirror --upstream https://stg.pawrrtal.dev --strict-timing \\
          conversations send "ping" --new --model litellm:openai/gpt-4o-mini
    """
    extra = list(ctx.args)
    if not extra:
        raise LocalError(
            "Missing command to mirror. Example: paw mirror --upstream URL auth status",
            hint="Append the paw subcommand after the --upstream flag.",
        )

    local_url = local or os.environ.get("PAW_BACKEND_URL") or DEFAULT_LOCAL_BACKEND_URL
    wrapped_args = _inject_json_flag(extra)
    ignored_event_types = _merge_ignore_lists(ignore)

    parent_config_root = config_root()
    sides = _allocate_side_dirs(parent_config_root, persona_prefix, local_url, upstream)
    try:
        results = asyncio.run(_run_both_sides(wrapped_args, sides))
    finally:
        if not keep_personas:
            _cleanup_side_dirs(sides)

    diff = _diff_results(
        results[0],
        results[1],
        ignored_event_types=ignored_event_types,
        strict_timing=strict_timing,
        strict_timing_threshold_ms=DEFAULT_STRICT_TIMING_THRESHOLD_MS,
    )
    exit_code = _resolve_exit_code(results, diff)

    if json_output:
        emit_json(_serialise_payload(results, diff, exit_code))
    else:
        _emit_human_summary(results, diff, exit_code)

    if exit_code != MIRROR_EXIT_SUCCESS:
        raise typer.Exit(code=exit_code)


def _inject_json_flag(wrapped_args: list[str]) -> list[str]:
    """Append ``--json`` if the wrapped command doesn't already pass it.

    We need machine-parseable output from both children so the semantic
    diff can compare event counts + ``final_text``. If the wrapped
    subcommand doesn't support ``--json`` (rare; ``doctor`` is one),
    the children will exit non-zero and the literal fallback kicks in.
    """
    if "--json" in wrapped_args:
        return list(wrapped_args)
    return [*wrapped_args, "--json"]


def _merge_ignore_lists(user_ignored: list[str]) -> set[str]:
    """Combine the user's ``--ignore`` flags with the default exclusions."""
    return {*DEFAULT_IGNORED_EVENT_TYPES, *user_ignored}


def _allocate_side_dirs(
    parent_config_root: Path,
    prefix: str,
    local_url: str,
    upstream_url: str,
) -> list[tuple[SideLabel, str, str, Path]]:
    """Reserve the per-side config dir + profile name for both children.

    Each side runs with its own ``PAW_CONFIG_DIR`` so cookies + persona
    state never collide with the parent process or sibling side.
    """
    sides: list[tuple[SideLabel, str, str, Path]] = []
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
    local. ``PAW_CONFIG_DIR`` redirects the state file to this side's
    isolated directory (see ``config.config_root``).
    """
    original_config_dir = os.environ.get("PAW_CONFIG_DIR")
    os.environ["PAW_CONFIG_DIR"] = str(side_dir)
    try:
        state = PersonaState(profile=profile, api_base_url=backend_url)
        state.save()
    finally:
        if original_config_dir is None:
            os.environ.pop("PAW_CONFIG_DIR", None)
        else:
            os.environ["PAW_CONFIG_DIR"] = original_config_dir


def _cleanup_side_dirs(sides: list[tuple[SideLabel, str, str, Path]]) -> None:
    """Remove every per-side directory we allocated this run."""
    for _, _, _, side_dir in sides:
        try:
            shutil.rmtree(side_dir, ignore_errors=False)
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Failed to remove mirror side dir", extra={"path": str(side_dir)})


async def _run_both_sides(
    wrapped_args: list[str],
    sides: list[tuple[SideLabel, str, str, Path]],
) -> list[SideResult]:
    """Spawn local + upstream children in parallel and gather their results."""
    tasks = [
        asyncio.create_task(_run_side(label, profile, backend_url, side_dir, wrapped_args))
        for label, profile, backend_url, side_dir in sides
    ]
    return await asyncio.gather(*tasks)


async def _run_side(
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
        parsed=_try_parse_json_payload(stdout),
    )


def _build_child_env(profile: str, side_dir: Path, backend_url: str) -> dict[str, str]:
    """Compose the env passed to one side's child subprocess.

    - ``PAW_CONFIG_DIR`` isolates cookies + persona state per side.
    - ``PAW_PROFILE`` carries the slot's profile name.
    - ``PAW_BACKEND_URL`` is the whole point of mirror — each side
      points at a different backend so we can diff their responses.
    """
    env = dict(os.environ)
    env["PAW_CONFIG_DIR"] = str(side_dir)
    env["PAW_PROFILE"] = profile
    env["PAW_BACKEND_URL"] = backend_url
    return env


def _try_parse_json_payload(stdout: str) -> dict[str, Any] | None:
    """Return the parsed JSON dict from a child's stdout, or ``None``.

    ``paw <subcmd> --json`` always emits a single JSON document on the
    last non-empty line. We tolerate stderr-style progress mixed into
    stdout by walking lines from the bottom up.
    """
    for raw_line in reversed(stdout.strip().splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None
    return None


def _diff_results(
    local_result: SideResult,
    upstream_result: SideResult,
    *,
    ignored_event_types: set[str],
    strict_timing: bool,
    strict_timing_threshold_ms: int,
) -> DiffOutcome:
    """Compare both sides and report whether they drifted.

    Picks the semantic diff when both sides parsed as JSON dicts;
    falls back to literal stdout + exit-code equality otherwise.
    """
    if local_result.parsed is None or upstream_result.parsed is None:
        return _diff_literal(local_result, upstream_result)
    return _diff_semantic(
        local_result.parsed,
        upstream_result.parsed,
        local_duration_ms=local_result.duration_ms,
        upstream_duration_ms=upstream_result.duration_ms,
        ignored_event_types=ignored_event_types,
        strict_timing=strict_timing,
        strict_timing_threshold_ms=strict_timing_threshold_ms,
    )


def _diff_literal(local_result: SideResult, upstream_result: SideResult) -> DiffOutcome:
    """Fallback diff for non-JSON children: stdout + exit code equality."""
    stdout_equal = local_result.stdout == upstream_result.stdout
    exit_equal = local_result.exit_code == upstream_result.exit_code
    has_drift = not (stdout_equal and exit_equal)
    return DiffOutcome(
        has_drift=has_drift,
        mode="literal",
        details={
            "stdout_equal": stdout_equal,
            "exit_code_equal": exit_equal,
            "local_exit_code": local_result.exit_code,
            "upstream_exit_code": upstream_result.exit_code,
        },
    )


def _diff_semantic(
    local_payload: dict[str, Any],
    upstream_payload: dict[str, Any],
    *,
    local_duration_ms: int,
    upstream_duration_ms: int,
    ignored_event_types: set[str],
    strict_timing: bool,
    strict_timing_threshold_ms: int,
) -> DiffOutcome:
    """Per-field diff for parsed ``conversations send`` payloads (and similar).

    Compares event-type counts (skipping ignored types), ``final_text``
    equality, and — only with ``--strict-timing`` — a wall-clock delta.
    """
    event_diff = _diff_event_counts(
        local_payload.get("events"),
        upstream_payload.get("events"),
        ignored_event_types=ignored_event_types,
    )
    final_text_equal = local_payload.get("final_text") == upstream_payload.get("final_text")
    duration_delta_ms = abs(local_duration_ms - upstream_duration_ms)
    timing_drift = strict_timing and duration_delta_ms > strict_timing_threshold_ms

    has_drift = bool(event_diff) or not final_text_equal or timing_drift
    details: dict[str, Any] = {
        "event_count_diff": event_diff,
        "final_text_equal": final_text_equal,
        "duration_delta_ms": duration_delta_ms,
        "timing_drift": timing_drift,
        "ignored_event_types": sorted(ignored_event_types),
    }
    return DiffOutcome(has_drift=has_drift, mode="semantic", details=details)


def _diff_event_counts(
    local_events: Any,
    upstream_events: Any,
    *,
    ignored_event_types: set[str],
) -> dict[str, dict[str, int]]:
    """Return a per-event-type {local, upstream} delta dict.

    Only event types that differ between the two sides appear in the
    result. Ignored types are dropped before comparison.
    """
    local_counts = _normalise_event_counts(local_events, ignored_event_types)
    upstream_counts = _normalise_event_counts(upstream_events, ignored_event_types)
    all_keys = set(local_counts) | set(upstream_counts)
    diff: dict[str, dict[str, int]] = {}
    for key in sorted(all_keys):
        local_value = local_counts.get(key, 0)
        upstream_value = upstream_counts.get(key, 0)
        if local_value != upstream_value:
            diff[key] = {"local": local_value, "upstream": upstream_value}
    return diff


def _normalise_event_counts(
    raw: Any,
    ignored_event_types: set[str],
) -> dict[str, int]:
    """Coerce a raw ``events`` field into a {type: count} dict, dropping ignored types."""
    if not isinstance(raw, dict):
        return {}
    counts: dict[str, int] = {}
    for event_type, count in raw.items():
        if not isinstance(event_type, str) or event_type in ignored_event_types:
            continue
        if not isinstance(count, int):
            continue
        counts[event_type] = count
    return counts


def _resolve_exit_code(results: list[SideResult], diff: DiffOutcome) -> int:
    """Map (child outcomes, drift) onto the mirror-specific exit codes."""
    if any(r.exit_code != 0 for r in results):
        return MIRROR_EXIT_CHILD_FAILED
    if diff.has_drift:
        return MIRROR_EXIT_DRIFT
    return MIRROR_EXIT_SUCCESS


def _serialise_payload(
    results: list[SideResult],
    diff: DiffOutcome,
    exit_code: int,
) -> dict[str, Any]:
    """Stable JSON shape for ``--json`` mode."""
    by_label = {r.label: r for r in results}
    return {
        "local": _serialise_side(by_label["local"]),
        "upstream": _serialise_side(by_label["upstream"]),
        "diff": {
            "mode": diff.mode,
            "has_drift": diff.has_drift,
            "details": diff.details,
        },
        "exit_code": exit_code,
    }


def _serialise_side(result: SideResult) -> dict[str, Any]:
    """One side's JSON dict — preserves parsed payload when available."""
    return {
        "label": result.label,
        "backend_url": result.backend_url,
        "profile": result.profile,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
        "parsed": result.parsed,
    }


def _emit_human_summary(
    results: list[SideResult],
    diff: DiffOutcome,
    exit_code: int,
) -> None:
    """Render a compact per-side summary plus the diff verdict."""
    for result in results:
        emit_human(_format_side_row(result))
    emit_human(_format_diff_verdict(diff, exit_code))


def _format_side_row(result: SideResult) -> str:
    """One line per side: label, backend, exit, duration."""
    return (
        f"[{result.label:>8}] backend={result.backend_url} "
        f"profile={result.profile} exit={result.exit_code} "
        f"duration={result.duration_ms}ms"
    )


def _format_diff_verdict(diff: DiffOutcome, exit_code: int) -> str:
    """Final-line verdict the operator sees after both sides run."""
    if exit_code == MIRROR_EXIT_CHILD_FAILED:
        return "mirror: child failed; no diff produced. See per-side stderr above."
    if not diff.has_drift:
        return f"mirror: no drift detected ({diff.mode} diff)."
    return f"mirror: drift detected ({diff.mode} diff) — details: {diff.details}"
