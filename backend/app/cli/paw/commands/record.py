"""paw record — capture HTTP traffic from any paw subcommand to a JSONL fixture.

The recording is performed inside :class:`PawClient` via an httpx event hook
gated by the :data:`RECORD_ENV_VAR` env var. ``paw record`` is just the thin
wrapper that sets the env var, invokes the wrapped command in-process, then
restores the env.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from app.cli.paw.errors import LocalError
from app.cli.paw.http import RECORD_ENV_VAR

app = typer.Typer(
    help="Record HTTP fixtures for any paw subcommand.",
    invoke_without_command=False,
    add_help_option=True,
    no_args_is_help=False,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


def record(
    ctx: typer.Context,
    to: Path = typer.Option(..., "--to", help="JSONL fixture path to append captured rows to."),
) -> None:
    """Re-invoke the wrapped paw command with ``PAW_RECORD=<to>`` set.

    Examples:
      paw record --to /tmp/login.jsonl auth status --json
      paw record --to /tmp/conv.jsonl conversations ls --json
    """
    extra = list(ctx.args)
    if not extra:
        raise LocalError(
            "Missing command to record. Example: paw record --to fix.jsonl auth status",
            hint="Append the paw subcommand after --to.",
        )
    to.parent.mkdir(parents=True, exist_ok=True)
    # Lazy import: main imports this module to register the command, so a
    # top-level `from app.cli.paw.main import app` would create a cycle.
    from app.cli.paw.main import app as paw_app  # noqa: PLC0415

    previous = os.environ.get(RECORD_ENV_VAR)
    os.environ[RECORD_ENV_VAR] = str(to)
    try:
        # Invoke in-process so we share the test fixture & current python
        # interpreter; subprocess re-entry would force a fresh argv parse
        # but loses the running cookie jar context.
        rc = paw_app(args=extra, standalone_mode=False)
    finally:
        if previous is None:
            os.environ.pop(RECORD_ENV_VAR, None)
        else:
            os.environ[RECORD_ENV_VAR] = previous
    if isinstance(rc, int) and rc != 0:
        raise typer.Exit(code=rc)
