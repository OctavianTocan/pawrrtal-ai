"""Output emitters for ``paw mirror`` (human, JSON, plain TSV)."""

from __future__ import annotations

from typing import Any

from app.cli.paw.commands.mirror.diff import DiffOutcome, SideResult
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

# Mirror-specific exit codes — see ``cli.py`` for the canonical comment.
MIRROR_EXIT_SUCCESS = 0
MIRROR_EXIT_LOCAL_ERROR = 1
MIRROR_EXIT_DRIFT = 6

# Max characters of ``final_text`` rendered in the ``--plain`` preview.
PLAIN_FINAL_TEXT_PREVIEW_CHARS = 80


def serialise_payload(
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


def emit_json_summary(
    results: list[SideResult],
    diff: DiffOutcome,
    exit_code: int,
) -> None:
    """Emit the JSON payload to stdout."""
    emit_json(serialise_payload(results, diff, exit_code))


def emit_human_summary(
    results: list[SideResult],
    diff: DiffOutcome,
    exit_code: int,
) -> None:
    """Render a compact per-side summary plus the diff verdict."""
    for result in results:
        emit_human(_format_side_row(result))
    emit_human(_format_diff_verdict(diff, exit_code))


def emit_plain_summary(results: list[SideResult]) -> None:
    """Emit one TSV row per side: slot, exit, duration_ms, final_text_preview.

    Pipe-friendly mode for shell pipelines that just want the headline
    numbers without parsing JSON.
    """
    rows = [_plain_row_for(result) for result in results]
    emit_plain_rows(rows)


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


def _format_side_row(result: SideResult) -> str:
    """One line per side: label, backend, exit, duration."""
    return (
        f"[{result.label:>8}] backend={result.backend_url} "
        f"profile={result.profile} exit={result.exit_code} "
        f"duration={result.duration_ms}ms"
    )


def _format_diff_verdict(diff: DiffOutcome, exit_code: int) -> str:
    """Final-line verdict the operator sees after both sides run."""
    if exit_code == MIRROR_EXIT_LOCAL_ERROR:
        return "mirror: child failed; no diff produced. See per-side stderr above."
    if not diff.has_drift:
        return f"mirror: no drift detected ({diff.mode} diff)."
    return f"mirror: drift detected ({diff.mode} diff) — details: {diff.details}"


def _plain_row_for(result: SideResult) -> tuple[str, int, int, str]:
    """Single TSV row: (label, exit_code, duration_ms, final_text_preview)."""
    preview = _final_text_preview(result)
    return (result.label, result.exit_code, result.duration_ms, preview)


def _final_text_preview(result: SideResult) -> str:
    """Truncated, whitespace-collapsed ``final_text`` for the plain row.

    Falls back to an empty string when the child didn't emit a JSON
    payload with a ``final_text`` field.
    """
    if result.parsed is None:
        return ""
    final_text = result.parsed.get("final_text")
    if not isinstance(final_text, str):
        return ""
    collapsed = " ".join(final_text.split())
    if len(collapsed) <= PLAIN_FINAL_TEXT_PREVIEW_CHARS:
        return collapsed
    return collapsed[:PLAIN_FINAL_TEXT_PREVIEW_CHARS] + "…"
