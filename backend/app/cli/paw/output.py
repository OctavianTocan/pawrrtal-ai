"""Three output modes: human (default), JSON, plain TSV."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from typing import Any


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
