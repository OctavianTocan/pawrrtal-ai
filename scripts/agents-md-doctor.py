#!/usr/bin/env python3
"""Health check for the agent's identity files (SOUL/AGENTS/USER/IDENTITY).

The system prompt assembled by ``app.tools.agents_md`` reads from
``SOUL.md`` and ``AGENTS.md`` at the workspace root.  Those files
silently grow over time as the agent (or the operator) appends
guidance, identities drift, and user notes accumulate — until one day
they push the prompt past a useful size and start eating the context
window.

This script is the doctor for that drift.  Run it against any
workspace directory and get a per-file report:

  - byte size              (raw on disk)
  - line count
  - estimated token count  (chars / 4 — same heuristic OpenAI publishes
                            for English; close enough for this purpose)
  - status                 (OK / WARN / FAIL relative to thresholds)

Soft threshold: 8 KB per file.  Hard threshold: 64 KB
(``_MAX_BYTES`` in ``app.tools.agents_md`` — anything above this
is silently truncated when assembled into the prompt, so files past
that point are losing content the agent will never see).

Future plans (not in this PR):
  - expose as an in-product ``/doctor`` tool the agent can call to
    self-check before suggesting an edit.
  - dedup detection (sections whose normalised body matches another
    section in the same file).

Usage::

    python scripts/agents-md-doctor.py                  # uses cwd
    python scripts/agents-md-doctor.py /path/to/workspace
    python scripts/agents-md-doctor.py --json /workspace # machine-readable

Exit codes:

  0 — every checked file is within the soft threshold
  1 — at least one file is above the soft threshold but under the hard
      cap (warning territory)
  2 — at least one file is at or above the hard cap (truncated when
      assembled into the system prompt)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Files we check, in the order we report them.  Mirrors
# ``app.tools.agents_md.PROTECTED_FILENAMES`` plus the canonical
# ordering used when assembling the system prompt (SOUL first).
IDENTITY_FILES: tuple[str, ...] = ("SOUL.md", "AGENTS.md", "USER.md", "IDENTITY.md")

# Soft + hard thresholds in BYTES.
SOFT_LIMIT = 8_000
HARD_LIMIT = 64_000  # mirrors agents_md._MAX_BYTES — past this we truncate

# Token estimate: 4 chars/token is the OpenAI rule of thumb for English
# text and it's good enough for a budget signal.  We deliberately don't
# pull in tiktoken here — the script must run with no extra deps so it
# can live next to the repo's other plain-Python lints.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class FileReport:
    """One identity-file's measurements + status."""

    name: str
    exists: bool
    bytes: int
    lines: int
    est_tokens: int
    status: str  # "missing" | "ok" | "warn" | "fail"


def _measure(path: Path) -> FileReport:
    if not path.is_file():
        return FileReport(
            name=path.name, exists=False, bytes=0, lines=0, est_tokens=0, status="missing"
        )
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    size = len(raw)
    if size >= HARD_LIMIT:
        status = "fail"
    elif size >= SOFT_LIMIT:
        status = "warn"
    else:
        status = "ok"
    return FileReport(
        name=path.name,
        exists=True,
        bytes=size,
        lines=lines,
        est_tokens=size // CHARS_PER_TOKEN,
        status=status,
    )


def _format_text(reports: list[FileReport]) -> str:
    """Pretty-printed report for humans."""
    lines: list[str] = []
    lines.append(
        f"agents-md-doctor — soft={SOFT_LIMIT:,}B  hard={HARD_LIMIT:,}B (truncation cap)"
    )
    lines.append("")
    lines.append(f"  {'file':<14} {'status':<8} {'bytes':>8} {'lines':>7} {'~tokens':>8}")
    lines.append(f"  {'-' * 14} {'-' * 8} {'-' * 8} {'-' * 7} {'-' * 8}")
    for r in reports:
        if r.status == "missing":
            lines.append(f"  {r.name:<14} {'MISSING':<8} {'-':>8} {'-':>7} {'-':>8}")
            continue
        glyph = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}[r.status]
        lines.append(
            f"  {r.name:<14} {glyph:<8} {r.bytes:>8,} {r.lines:>7,} {r.est_tokens:>8,}"
        )
    return "\n".join(lines)


def _exit_code(reports: list[FileReport]) -> int:
    statuses = {r.status for r in reports}
    if "fail" in statuses:
        return 2
    if "warn" in statuses:
        return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="Workspace directory to inspect (default: current working directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON report instead of the human-readable table.",
    )
    args = parser.parse_args(argv[1:])

    root = Path(args.workspace).resolve()
    if not root.is_dir():
        print(f"agents-md-doctor: not a directory: {root}", file=sys.stderr)
        return 2

    reports = [_measure(root / name) for name in IDENTITY_FILES]

    if args.json:
        payload = {
            "workspace": str(root),
            "soft_limit": SOFT_LIMIT,
            "hard_limit": HARD_LIMIT,
            "files": [asdict(r) for r in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_format_text(reports))

    code = _exit_code(reports)
    if code == 1 and not args.json:
        print("\nWARN: at least one file exceeds the soft limit (8 KB).", file=sys.stderr)
    elif code == 2 and not args.json:
        print(
            "\nFAIL: at least one file exceeds the hard limit (64 KB) — content past that "
            "point is truncated when assembled into the agent's system prompt.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
