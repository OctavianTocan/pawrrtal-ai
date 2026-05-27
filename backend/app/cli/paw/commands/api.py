"""paw api — generic HTTP passthrough + OpenAPI discovery.

The escape hatch for backend endpoints that don't yet have an opinionated
``paw`` verb. Uses the persona's cookie jar + base URL so the call is
authenticated identically to every other paw command.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import httpx
import typer

from app.cli.paw.config import PersonaState
from app.cli.paw.errors import ApiError, AuthError, LocalError
from app.cli.paw.http import HTTP_UNAUTHORIZED, PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

HTTP_OK_MIN = 200
HTTP_OK_MAX = 299

app = typer.Typer(
    help="Generic HTTP passthrough + OpenAPI discovery.",
    no_args_is_help=True,
)


def _parse_header(raw: str) -> tuple[str, str]:
    """Parse a ``K: V`` curl-style header literal."""
    if ":" not in raw:
        raise LocalError(
            f"Bad header {raw!r}; expected 'Key: Value'.",
            hint="Use curl-style headers: -H 'X-Foo: bar'.",
        )
    key, value = raw.split(":", 1)
    return key.strip(), value.strip()


def _parse_body(literal: str | None, from_stdin: bool) -> Any | None:
    """Resolve the request body: literal JSON, stdin JSON, or absent."""
    if literal is not None and from_stdin:
        raise LocalError(
            "Pass -d/--data or --stdin, not both.",
            hint="Choose one body source.",
        )
    raw: str | None
    if literal is not None:
        raw = literal
    elif from_stdin:
        raw = sys.stdin.read()
    else:
        return None
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise LocalError(
            f"Body is not valid JSON: {e}",
            hint="Wrap strings in double quotes; verify shell escaping.",
        ) from e


@app.command(
    "request",
    help="Issue an arbitrary HTTP request against the backend.",
)
def request(
    method: str = typer.Argument(..., help="HTTP method (GET/POST/PUT/PATCH/DELETE)."),
    path: str = typer.Argument(..., help="Path including leading slash, e.g. /api/v1/users/me."),
    data: str | None = typer.Option(None, "--data", "-d", help="Literal JSON body."),
    from_stdin: bool = typer.Option(False, "--stdin", help="Read JSON body from stdin."),
    header: list[str] = typer.Option(
        [], "--header", "-H", help="Repeatable curl-style header 'K: V'."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Wire-trace to stderr."),
    profile: str = typer.Option("default", "--profile"),
    workspace: str | None = typer.Option(
        None, "--workspace", help="Override the persona's workspace ID for this call."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit {status, headers, body} envelope; default is raw body."
    ),
) -> None:
    """Issue a single HTTP request via the persona's session.

    Exit codes: 0 on 2xx, 3 on 401, 5 on other 4xx/5xx.

    Examples:
      paw api request GET /api/v1/users/me --json
      paw api request POST /api/v1/conversations --stdin < body.json
      paw api request POST /api/v1/x -H 'X-Trace: 1' -d '{"k":1}'
    """
    headers = dict(_parse_header(raw) for raw in header)
    body = _parse_body(data, from_stdin)
    state = PersonaState.load(profile)
    if workspace is not None:
        state.default_workspace_id = workspace
    resp = asyncio.run(_send(state, method.upper(), path, body, headers, verbose=verbose))
    _emit_response(resp, json_out=json_out)


@app.command("openapi", help="Fetch the FastAPI OpenAPI document.")
def openapi(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json", help="Emit the full schema as JSON."),
) -> None:
    """Fetch /openapi.json. Default human mode lists every route once per line.

    Examples:
      paw api openapi
      paw api openapi --json
    """
    state = PersonaState.load(profile)
    schema = asyncio.run(_fetch_openapi(state))
    if json_out:
        emit_json(schema)
        return
    for method, route_path in _routes_from_schema(schema):
        emit_human(f"{method:<6} {route_path}")


@app.command("ls", help="List API routes (TSV-friendly).")
def ls(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain", help="TSV output without headers."),
) -> None:
    """Same data as ``openapi`` but only the route inventory.

    Examples:
      paw api ls
      paw api ls --plain
      paw api ls --json
    """
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )
    state = PersonaState.load(profile)
    schema = asyncio.run(_fetch_openapi(state))
    routes = list(_routes_from_schema(schema))
    if json_out:
        emit_json([{"method": m, "path": p} for m, p in routes])
        return
    if plain:
        emit_plain_rows(routes)
        return
    for method, route_path in routes:
        emit_human(f"{method:<6} {route_path}")


async def _send(
    state: PersonaState,
    method: str,
    path: str,
    body: Any | None,
    headers: dict[str, str],
    *,
    verbose: bool,
) -> httpx.Response:
    """Issue the request and translate transport/HTTP failures to PawError."""
    async with PawClient(state, verbose=verbose) as client:
        resp = await client.request(
            method,
            path,
            json_body=body,
            headers=headers or None,
            expect=(),
        )
    if HTTP_OK_MIN <= resp.status_code <= HTTP_OK_MAX:
        return resp
    if resp.status_code == HTTP_UNAUTHORIZED:
        raise AuthError(f"{method} {path} -> 401: {resp.text[:200]}")
    raise ApiError(f"{method} {path} -> {resp.status_code}: {resp.text[:200]}")


async def _fetch_openapi(state: PersonaState) -> dict[str, Any]:
    """GET the root /openapi.json document; FastAPI mounts it there by default."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/openapi.json", expect=(200,))
    schema = resp.json()
    if not isinstance(schema, dict):
        raise ApiError("OpenAPI schema is not a JSON object.")
    return schema


def _routes_from_schema(schema: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten ``paths`` into (METHOD, path) tuples, sorted by path then method."""
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        return []
    valid_methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    routes: list[tuple[str, str]] = []
    for route_path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        routes.extend(
            (method.upper(), route_path) for method in ops if method.lower() in valid_methods
        )
    routes.sort(key=lambda item: (item[1], item[0]))
    return routes


def _emit_response(resp: httpx.Response, *, json_out: bool) -> None:
    """Render an HTTP response per the user's output mode."""
    if json_out:
        body: Any
        try:
            body = resp.json()
        except json.JSONDecodeError:
            body = resp.text
        emit_json(
            {
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "body": body,
            }
        )
        return
    sys.stdout.write(resp.text)
    if not resp.text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
