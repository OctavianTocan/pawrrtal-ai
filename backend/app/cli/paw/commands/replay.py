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

# SSE frames are joined with this delimiter to reconstruct the wire stream
# the consumer originally saw. Mirrors ``FRAME_DELIMITER`` in
# ``app.cli.paw.sse`` — the byte-level framer there re-splits on the same
# delimiter, so replay round-trips through the same code path as live.
SSE_FRAME_DELIMITER = b"\n\n"

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

    http_rows = [row for row in rows if row.get("type") not in {"sse", "sse_done"}]
    sse_bodies = _build_sse_bodies(rows)
    base_urls = {_base_url(row["url"]) for row in http_rows}
    with respx.mock(assert_all_called=False) as r:
        _mount_rows(r, http_rows, sse_bodies)
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


def _build_sse_bodies(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[bytes]]:
    r"""Collect captured SSE frames into one reconstructed body per stream row.

    Keyed by ``(method, url)`` so two methods hitting the same URL don't
    share bodies. **One body is emitted per ``is_stream=True`` HTTP envelope
    row** — not one body per URL — so multi-turn fixtures that re-POST the
    same streaming endpoint (e.g. two ``conversations send`` calls in one
    recording) replay with distinct per-turn bodies. Without this, every
    chat turn was keyed by URL alone and the first POST greedily consumed
    every captured frame while subsequent POSTs got an empty body that the
    framer silently decoded as zero events.

    The recorder writes the HTTP envelope row first (httpx response hook
    fires at response start) and then appends one ``type=sse`` row per
    frame until the stream closes. So the frames that belong to a given
    envelope are the ``type=sse`` rows between that envelope and the next
    streaming envelope for the same key (or EOF). The walk below tracks
    the most-recent stream envelope per ``(method, url)`` and materialises
    its body when the next envelope for the same key arrives, plus once
    more at EOF for the final envelope.
    """
    open_body_index: dict[tuple[str, str], int] = {}
    bodies: dict[tuple[str, str], list[bytes]] = defaultdict(list)
    frame_buffer: dict[tuple[str, str], list[bytes]] = defaultdict(list)

    def _flush(key: tuple[str, str]) -> None:
        """Materialize the pending frame buffer into the currently-open body slot."""
        idx = open_body_index.get(key)
        if idx is None:
            return
        frames = frame_buffer.pop(key, [])
        body = SSE_FRAME_DELIMITER.join(frames) + SSE_FRAME_DELIMITER if frames else b""
        bodies[key][idx] = body

    for row in rows:
        row_type = row.get("type")
        if row_type == "sse":
            method = str(row.get("method", "POST")).upper()
            url = str(row["url"])
            frame = base64.b64decode(str(row["frame_b64"]))
            frame_buffer[(method, url)].append(frame)
            continue
        if row_type == "sse_done":
            # Legacy/future terminator marker; reserved for richer replay flows.
            continue
        if not row.get("is_stream"):
            continue
        method = str(row["method"]).upper()
        url = str(row["url"])
        key = (method, url)
        # The previous open envelope (if any) for this key now collects
        # no more frames — flush it before reserving a slot for this one.
        _flush(key)
        bodies[key].append(b"")
        open_body_index[key] = len(bodies[key]) - 1
    for key in list(open_body_index.keys()):
        _flush(key)
    return bodies


def _build_streaming_response(status: int, headers: dict[str, Any], body: bytes) -> httpx.Response:
    """Build an httpx.Response whose iter_bytes yields ``body`` once.

    httpx happily streams a pre-materialized ``content=`` payload back
    through ``aiter_bytes`` (one chunk), so the consumer's frame reassembly
    runs end-to-end against the captured bytes.
    """
    return httpx.Response(status, headers=dict(headers), content=body)


def _mount_rows(
    router: respx.MockRouter,
    rows: list[dict[str, Any]],
    sse_bodies: dict[tuple[str, str], list[bytes]],
) -> None:
    """Group recorded rows by (METHOD, URL) and mount them as respx side effects.

    Multiple rows with the same key replay in recorded order so flows that
    re-poll an endpoint surface different snapshots on each call. Streaming
    rows consume one ``sse_bodies`` entry each — same ``(method, url)`` key
    used by ``_build_sse_bodies`` — so per-turn bodies stay distinct.
    """
    grouped: dict[tuple[str, str], list[httpx.Response]] = defaultdict(list)
    for row in rows:
        method = str(row["method"]).upper()
        url = str(row["url"])
        status = int(row["status"])
        headers = row.get("response_headers") or {}
        is_stream = bool(row.get("is_stream"))
        if is_stream:
            pending = sse_bodies.get((method, url)) or []
            body = pending.pop(0) if pending else b""
            grouped[(method, url)].append(_build_streaming_response(status, headers, body))
            continue
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
