#!/usr/bin/env python3
"""Architectural gate: providers must NOT import from ``app.tools.*``.

The agent-loop architecture is provider-neutral: providers translate
the cross-provider :class:`app.agents.types.AgentTool` shape
into their SDK's tool format, but they don't reach into specific tool
factories.  Tool composition (which tools the agent gets this turn)
lives in the chat router (``app/api/chat.py``).

Why enforce in CI rather than just code review:

  * It's an easy mistake to make — ``settings.exa_api_key`` is already
    in scope inside providers, so "just append Exa here" is a single
    line that escapes review.
  * Once it leaks once, every new provider copy-pastes the smell.
  * Future per-agent permission gating must live above the providers;
    a tool import inside a provider silently breaks that contract.

What this script enforces:

  * Files under ``backend/app/core/providers/`` MAY NOT import any
    module whose dotted path starts with ``app.tools.``.
  * Provider-internal *bridges* live next to the provider as
    ``providers/_*_tool_bridge.py`` and are allowed — they translate
    the abstract :class:`AgentTool` shape and are NOT imports of
    concrete tool factories.

Usage::

    python scripts/check-no-tools-in-providers.py    # default
    python scripts/check-no-tools-in-providers.py --verbose

Exit codes:

  0 — every provider file is clean
  1 — at least one offender; offending lines are printed
"""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROVIDERS_DIR = REPO_ROOT / "backend" / "app" / "core" / "providers"

# Forbidden import-prefix (matches ``import app.tools.X`` and
# ``from app.tools[.X] import Y``).
FORBIDDEN_PREFIX = "app.tools"


@dataclass(frozen=True)
class Offender:
    path: Path
    line: int
    statement: str


def _iter_python_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".pytest_cache"}]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def _matches_forbidden(module: str | None) -> bool:
    if module is None:
        return False
    return module == FORBIDDEN_PREFIX or module.startswith(f"{FORBIDDEN_PREFIX}.")


def _check_file(path: Path) -> list[Offender]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    offenders: list[Offender] = []
    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _matches_forbidden(node.module):
            statement = source_lines[node.lineno - 1] if node.lineno - 1 < len(source_lines) else ""
            offenders.append(Offender(path=path, line=node.lineno, statement=statement.strip()))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_forbidden(alias.name):
                    statement = source_lines[node.lineno - 1] if node.lineno - 1 < len(source_lines) else ""
                    offenders.append(
                        Offender(path=path, line=node.lineno, statement=statement.strip())
                    )
                    break
    return offenders


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv[1:] or "-v" in argv[1:]

    if not PROVIDERS_DIR.exists():
        print(
            f"check-no-tools-in-providers: {PROVIDERS_DIR} not found; nothing to check",
            file=sys.stderr,
        )
        return 0

    offenders: list[Offender] = []
    files_checked = 0
    for py_file in _iter_python_files(PROVIDERS_DIR):
        files_checked += 1
        offenders.extend(_check_file(py_file))

    if not offenders:
        if verbose:
            print(
                f"check-no-tools-in-providers: OK ({files_checked} files clean)"
            )
        else:
            print("check-no-tools-in-providers: OK")
        return 0

    print(
        f"check-no-tools-in-providers: {len(offenders)} forbidden import(s):\n",
        file=sys.stderr,
    )
    for o in offenders:
        rel = o.path.relative_to(REPO_ROOT)
        print(f"  {rel}:{o.line}  {o.statement}", file=sys.stderr)
    print(
        "\nProviders must stay tool-agnostic.  Move the import into the chat router\n"
        "(`backend/app/api/chat.py`) or a non-provider module.  See\n"
        "`.claude/rules/architecture/no-tools-in-providers.md`.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
