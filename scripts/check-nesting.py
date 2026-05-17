#!/usr/bin/env python3
"""Repo-wide nesting-depth lint for Python sources.

Walks the backend tree and reports every function whose maximum
``if`` / ``for`` / ``while`` / ``try`` / ``with`` / ``match`` nesting
depth exceeds the configured budget (default: 3 — i.e. at most three
levels of compound-statement nesting inside a single function body).

Sibling to ``scripts/check-file-lines.mjs``; runs as part of the
``backend`` pre-commit + CI pipeline.

Usage::

    python scripts/check-nesting.py            # check the default tree
    MAX_DEPTH=2 python scripts/check-nesting.py  # tighter override

Exit codes:

  0 — every scanned function is within budget
  1 — at least one function exceeds the budget; offenders are printed

Why a custom script rather than a ruff/flake8 plugin: ``ruff`` has no
direct "max nesting depth" rule (the closest is the cognitive-complexity
family, which conflates several signals).  This is intentionally one
narrow signal — easy to read, easy to override, easy to remove if a
better off-the-shelf option lands.
"""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Roots we scan.  Add new top-level Python trees here.
SCAN_ROOTS = ("backend",)

# Directory names we never descend into.
SKIP_DIRECTORIES = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "build",
        "dist",
        "alembic",
        "tests",  # tests can nest more freely (e.g. parametrized assertions)
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

# Compound statements that count as a level of nesting.
NESTING_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)

DEFAULT_MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "3"))

# Repo-relative ``path::function`` keys that are exempt from the
# nesting budget.  Pre-existing tech debt — each entry should be
# tracked in a follow-up bean and removed once the function is
# flattened.  Mirror of the EXEMPT_PATH_FRAGMENTS pattern in
# ``scripts/check-file-lines.mjs``.
#
# DO NOT add new entries here as a workaround.  New code must come in
# under the budget; if you genuinely cannot, raise it in review.
EXEMPT_FUNCTIONS: frozenset[str] = frozenset(
    {
        # TODO(pawrrtal): flatten Gemini provider stream + helper.
        # `make_gemini_stream_fn` and its inner `stream_fn` close over
        # 6 levels because the Google SDK's event surface is a switch
        # statement nested inside the streaming for-loop.  Extract
        # event-type handlers (text / function-call / safety) into
        # module-level helpers.
        "backend/app/core/providers/gemini_provider.py::make_gemini_stream_fn",
        "backend/app/core/providers/gemini_provider.py::stream_fn",
        "backend/app/core/providers/gemini_provider.py::stream",
        # TODO(pawrrtal): flatten the agent loop's event drain.
        "backend/app/core/agent_loop/loop.py::_run_loop",
        # TODO(pawrrtal): flatten the Claude SDK event translators.
        # All three walk a discriminated union from the Anthropic SDK
        # via repeated isinstance checks; would benefit from a small
        # dispatch table.
        "backend/app/core/providers/claude_provider.py::_events_from_assistant",
        "backend/app/core/providers/claude_provider.py::_events_from_message",
        "backend/app/core/providers/claude_provider.py::_tool_result_to_text",
    }
)


@dataclass(frozen=True)
class Offender:
    """A function whose deepest nesting level breached the budget."""

    path: Path
    function: str
    line: int
    depth: int


def _max_depth(node: ast.AST, current: int = 0) -> int:
    """Return the max compound-stmt nesting depth reachable from *node*.

    *current* is the depth at which *node* itself sits (so the body of
    a top-level function is depth 0; an ``if`` directly inside it
    pushes its body to depth 1; an ``if`` inside that ``if`` reaches
    depth 2; etc).
    """
    deepest = current
    for child in ast.iter_child_nodes(node):
        if isinstance(child, NESTING_NODES):
            child_depth = _max_depth(child, current + 1)
        else:
            child_depth = _max_depth(child, current)
        if child_depth > deepest:
            deepest = child_depth
    return deepest


def _walk_functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def check_file(path: Path, max_depth: int) -> list[Offender]:
    """Return every function in *path* whose max nesting exceeds *max_depth*."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    offenders: list[Offender] = []
    rel = path.relative_to(REPO_ROOT).as_posix()
    for func in _walk_functions(tree):
        depth = _max_depth(func, current=0)
        if depth <= max_depth:
            continue
        key = f"{rel}::{func.name}"
        if key in EXEMPT_FUNCTIONS:
            continue
        offenders.append(
            Offender(path=path, function=func.name, line=func.lineno, depth=depth)
        )
    return offenders


def _iter_python_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # In-place mutation prunes the walk.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRECTORIES]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def main(argv: list[str]) -> int:
    max_depth = DEFAULT_MAX_DEPTH
    if len(argv) > 1:
        try:
            max_depth = int(argv[1])
        except ValueError:
            print(f"check-nesting: invalid max depth: {argv[1]!r}", file=sys.stderr)
            return 2

    offenders: list[Offender] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in _iter_python_files(root):
            offenders.extend(check_file(py_file, max_depth))

    if not offenders:
        print(f"check-nesting: OK (no functions exceed depth {max_depth})")
        return 0

    offenders.sort(key=lambda o: (-o.depth, str(o.path), o.line))
    print(
        f"check-nesting: {len(offenders)} function(s) exceed depth {max_depth}:\n",
        file=sys.stderr,
    )
    for offender in offenders:
        rel = offender.path.relative_to(REPO_ROOT)
        print(
            f"  depth={offender.depth}  {rel}:{offender.line}  in {offender.function}()",
            file=sys.stderr,
        )
    print(
        "\nFlatten with guard clauses or extract helpers to bring each function under the budget.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
