"""paw replay — mount a JSONL fixture as an in-process backend and run a paw command.

v1 limitation: replay is in-process only. The recorded routes are mounted via
respx and the command is invoked through typer's CliRunner. A subprocess /
real-port replay server is a v2 follow-up (see bean).
"""

from __future__ import annotations

import base64
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import respx
import typer

from app.cli.paw.errors import LocalError

app = typer.Typer(
    help="Replay a recorded JSONL fixture against a paw command.",
    no_args_is_help=False,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


def replay(
    ctx: typer.Context,
    fixture: Path = typer.Option(
        ..., "--from", help="JSONL fixture path produced by `paw record`."
    ),
) -> None:
    """Replay ``fixture`` while running the supplied paw subcommand.

    Examples:
      paw replay --from /tmp/login.jsonl auth status --json
      paw replay --from /tmp/conv.jsonl conversations ls --json
    """
    extra = list(ctx.args)
    if not extra:
        raise LocalError(
            "Missing command to replay. Example: paw replay --from fix.jsonl auth status",
            hint="Append the paw subcommand after --from.",
        )
    if not fixture.exists():
        raise LocalError(
            f"Fixture not found: {fixture}",
            hint="Use `paw record --to <path> <cmd>` to produce one.",
        )
    rows = _load_rows(fixture)
    if not rows:
        raise LocalError(
            f"Fixture {fixture} contains no rows.",
            hint="Record at least one request before replaying.",
        )
    # Lazy import: main imports this module to register the command, so a
    # top-level `from app.cli.paw.main import app` would create a cycle.
    from app.cli.paw.main import app as paw_app  # noqa: PLC0415

    base_urls = {_base_url(row["url"]) for row in rows}
    with respx.mock(assert_all_called=False) as r:
        _mount_rows(r, rows)
        # When the fixture targets a single backend, expose a hint via
        # respx so commands without an explicit --api still resolve. Persona
        # state still drives the actual URL the command will hit.
        _ = base_urls
        rc = paw_app(args=extra, standalone_mode=False)
    if isinstance(rc, int) and rc != 0:
        raise typer.Exit(code=rc)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL fixture into a list of recorded rows."""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _base_url(url: str) -> str:
    """Return the scheme://host portion of ``url`` for respx mount targeting."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _mount_rows(router: respx.MockRouter, rows: list[dict[str, Any]]) -> None:
    """Group recorded rows by (METHOD, URL) and mount them as respx side effects.

    Multiple rows with the same key replay in recorded order so flows that
    re-poll an endpoint surface different snapshots on each call.
    """
    grouped: dict[tuple[str, str], list[httpx.Response]] = defaultdict(list)
    for row in rows:
        method = str(row["method"])
        url = str(row["url"])
        status = int(row["status"])
        headers = row.get("response_headers") or {}
        body_text = row.get("response_body")
        body_b64 = row.get("response_body_bytes_b64")
        if isinstance(body_b64, str):
            content = base64.b64decode(body_b64)
            response = httpx.Response(status, headers=dict(headers), content=content)
        elif isinstance(body_text, str):
            response = httpx.Response(status, headers=dict(headers), text=body_text)
        else:
            response = httpx.Response(status, headers=dict(headers))
        grouped[(method, url)].append(response)
    for (method, url), responses in grouped.items():
        router.route(method=method, url=url).mock(side_effect=responses)
