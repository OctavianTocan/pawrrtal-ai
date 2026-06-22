"""Three output modes: human (default), JSON, plain TSV."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from typing import Any

from app.cli.paw.errors import LocalError

# <skill-gen>
# ---
# name: paw-extend
# description: Extend or maintain the paw CLI (backend/app/cli/paw/). Use when adding a new paw subcommand, a new verify suite, a new output mode, an orchestrator command (like fanout/mirror/dev), or refactoring the shared helpers (http.py, sse.py, output.py, errors.py). The user-facing skill is `paw` -- this one teaches you how the surface is built so the next addition fits the existing patterns instead of inventing parallels.
# ---
#
# ## Output modes
#
# Every new list-style verb must support:
#
# 1. Default human text: one line per row or a compact table. It may be lossy,
#    but it should be readable.
# 2. `--json`: full machine-readable payload. Failed commands emit
#    `{"error": "...", "code": <int>, "hint": "..."}` and exit non-zero.
# 3. `--plain`: TSV without headers for pipes. Skip only when the verb returns
#    a scalar or a single object's body.
#
# Use `emit_human`, `emit_json`, and `emit_plain_rows`. Do not print directly
# from command modules, because direct prints leak into `--json` output.
# </skill-gen>


def require_one_output_mode(*, json_out: bool, plain: bool) -> None:
    """Reject simultaneous --json + --plain. Mutually exclusive by design."""
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )


def emit_json(payload: Any) -> None:
    """Emit a single-line JSON dump terminated by newline."""
    json.dump(payload, sys.stdout, ensure_ascii=False, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


def emit_human(text: str) -> None:
    """Print human-readable text; ensure a trailing newline."""
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def emit_plain_rows(rows: Iterable[Iterable[Any]]) -> None:
    """TSV without a header row. Each row is tab-joined."""
    for row in rows:
        sys.stdout.write(
            "\t".join("" if c is None else str(c) for c in row),
        )
        sys.stdout.write("\n")
    sys.stdout.flush()
