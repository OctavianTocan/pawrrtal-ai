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

Exit code semantics follow the canonical conventions in ``errors.py``:

- ``0`` — both children succeeded AND no drift detected.
- ``1`` — one or both children exited non-zero (local orchestration error).
- ``6`` — both children succeeded but the diff found drift (verification failed).

Example::

    paw mirror --upstream https://dev.pawrrtal.dev \\
        conversations send "hello" --new \\
        --model litellm:openai/gpt-4o-mini
"""

from __future__ import annotations

import asyncio
import os

import typer

from app.cli.paw.commands.mirror.diff import (
    DEFAULT_IGNORED_EVENT_TYPES,
    DEFAULT_STRICT_TIMING_THRESHOLD_MS,
    DiffOutcome,
    SideResult,
    diff_results,
    merge_ignore_lists,
)
from app.cli.paw.commands.mirror.output import (
    MIRROR_EXIT_DRIFT,
    MIRROR_EXIT_LOCAL_ERROR,
    MIRROR_EXIT_SUCCESS,
    emit_human_summary,
    emit_json_summary,
    emit_plain_summary,
)
from app.cli.paw.commands.mirror.runner import (
    DEFAULT_PERSONA_PREFIX,
    allocate_side_dirs,
    cleanup_side_dirs,
    run_both_sides,
)
from app.cli.paw.config import config_root
from app.cli.paw.errors import LocalError

# Default local backend URL when the parent process has no PAW_BACKEND_URL
# set. Matches ``ENV_BASE_URLS["local"]`` in ``config.py`` so the help and
# behaviour stay aligned with the rest of the CLI.
DEFAULT_LOCAL_BACKEND_URL = "http://127.0.0.1:8000"

# Wrapped subcommands that do NOT support ``--json``. Appending the flag
# blindly turns ``paw mirror auth login`` into a typer parse error; we
# skip injection when the wrapped verb is in this set and rely on the
# literal-diff fallback instead.
_VERBS_WITHOUT_JSON: frozenset[str] = frozenset(
    {
        "auth",
        "logout",
        "doctor",
        "dev",
        "fanout",
        "mirror",
        "record",
        "replay",
    },
)


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
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON diff result instead of the human summary.",
    ),
    plain: bool = typer.Option(
        False,
        "--plain",
        help="Emit one TSV row per side (label, exit, duration_ms, final_text).",
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
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )

    local_url = local or os.environ.get("PAW_BACKEND_URL") or DEFAULT_LOCAL_BACKEND_URL
    wrapped_args = _inject_json_flag(extra)
    ignored_event_types = merge_ignore_lists(ignore)

    parent_config_root = config_root()
    sides = allocate_side_dirs(parent_config_root, persona_prefix, local_url, upstream)
    try:
        results = asyncio.run(run_both_sides(wrapped_args, sides))
    finally:
        if not keep_personas:
            cleanup_side_dirs(sides)

    diff = diff_results(
        results[0],
        results[1],
        ignored_event_types=ignored_event_types,
        strict_timing=strict_timing,
        strict_timing_threshold_ms=DEFAULT_STRICT_TIMING_THRESHOLD_MS,
    )
    exit_code = _resolve_exit_code(results, diff)

    if json_out:
        emit_json_summary(results, diff, exit_code)
    elif plain:
        emit_plain_summary(results)
    else:
        emit_human_summary(results, diff, exit_code)

    if exit_code != MIRROR_EXIT_SUCCESS:
        raise typer.Exit(code=exit_code)


def _inject_json_flag(wrapped_args: list[str]) -> list[str]:
    """Append ``--json`` if the wrapped command supports it and doesn't already pass it.

    We want machine-parseable output from both children so the semantic
    diff can compare event counts + ``final_text``. Some verbs
    (``auth``, ``doctor``, …) do not accept ``--json`` and would fail
    typer parsing if we appended it blindly — skip injection in that
    case and rely on the literal-diff fallback. The set of skip verbs
    is captured in ``_VERBS_WITHOUT_JSON``.
    """
    if not wrapped_args:
        return list(wrapped_args)
    if "--json" in wrapped_args:
        return list(wrapped_args)
    if wrapped_args[0] in _VERBS_WITHOUT_JSON:
        return list(wrapped_args)
    return [*wrapped_args, "--json"]


def _resolve_exit_code(results: list[SideResult], diff: DiffOutcome) -> int:
    """Map (child outcomes, drift) onto the canonical paw exit codes.

    - Any child failure → ``1`` (local orchestration error per ``errors.py``).
    - Drift between children → ``6`` (verification failed).
    - Otherwise → ``0``.
    """
    if any(r.exit_code != 0 for r in results):
        return MIRROR_EXIT_LOCAL_ERROR
    if diff.has_drift:
        return MIRROR_EXIT_DRIFT
    return MIRROR_EXIT_SUCCESS
