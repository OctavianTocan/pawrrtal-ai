"""Semantic + literal diff helpers for ``paw mirror``.

Both differs return a ``DiffOutcome``; the orchestrator picks which one
runs based on whether both sides parsed as JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

# Event types excluded from the semantic diff by default. ``usage`` is the
# canonical noisy event — token counts almost always differ across
# environments and are not actionable drift.
DEFAULT_IGNORED_EVENT_TYPES: tuple[str, ...] = ("usage",)

# Default threshold (ms) above which ``--strict-timing`` flags a duration
# delta as drift. Picked to be wider than typical p50 noise but narrow
# enough to catch a real provider regression.
DEFAULT_STRICT_TIMING_THRESHOLD_MS = 1000

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


def merge_ignore_lists(user_ignored: list[str]) -> set[str]:
    """Combine the user's ``--ignore`` flags with the default exclusions."""
    return {*DEFAULT_IGNORED_EVENT_TYPES, *user_ignored}


def try_parse_json_payload(stdout: str) -> dict[str, Any] | None:
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


def diff_results(
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
