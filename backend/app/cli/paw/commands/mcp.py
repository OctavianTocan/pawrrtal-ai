"""paw mcp — MCP server registry CRUD.

Drives the same backend surface as the Settings UI's MCP card
(``/api/v1/mcp/servers`` family). Bindings are scoped per user and
keyed by UUID. ``McpServerResponse`` carries ``id`` + ``name`` +
``status`` (``enabled`` | ``disabled``) + ``config`` (opaque JSON
forwarded to the external-MCP bridge).

Verbs:

- ``paw mcp list / ls``      GET /api/v1/mcp/servers
- ``paw mcp show <id>``      derived from the list response client-side
                              (no per-row GET endpoint exposed)
- ``paw mcp create``         POST /api/v1/mcp/servers
- ``paw mcp update <id>``    PATCH /api/v1/mcp/servers/{id}
- ``paw mcp delete <id>``    DELETE /api/v1/mcp/servers/{id}

Not implemented: ``paw mcp test``. The backend exposes no
ping/health endpoint per row today (the external-MCP bridge in
``app.core.tools.external_mcp`` is invoked only during a chat
turn). A test verb can be added later when a probe endpoint lands.

Output modes mirror ``paw channels`` / ``paw workspaces``:
``--json``, ``--plain``, default human-readable. Exit codes come
from ``app.cli.paw.errors``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import ApiError, LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

# Column widths for `paw mcp list` on an 80-col terminal: 36-char UUID,
# 24-char name, 10-char status, remainder reserved for a short
# fingerprint of config keys so the list is glanceable.
LS_ID_WIDTH = 36
LS_NAME_WIDTH = 24
LS_STATUS_WIDTH = 10

# Allowed values for the backend's ``status`` field. Mirrors the
# regex on ``McpServerPayload.status``; mismatch surfaces as a local
# error before the HTTP round-trip.
ALLOWED_STATUS = ("enabled", "disabled")

# Sole HTTP status code interpreted at this layer (delete-noop semantics).
HTTP_NOT_FOUND = 404

app = typer.Typer(
    help="Manage MCP server registry (list / show / create / update / delete).",
    no_args_is_help=True,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _parse_config(raw: str | None) -> dict[str, Any]:
    """Parse the ``--config`` JSON string into a dict; reject malformed input early."""
    if raw is None:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LocalError(
            f"Bad --config: {e.msg}.",
            hint='--config \'{"command":"npx","args":["..."]}\'',
        ) from e
    if not isinstance(parsed, dict):
        raise LocalError(
            "Bad --config: expected a JSON object.",
            hint='--config \'{"command":"npx"}\'',
        )
    return parsed


def _validate_status(status: str | None) -> None:
    """Reject a status value outside the backend's allowed set."""
    if status is not None and status not in ALLOWED_STATUS:
        raise LocalError(
            f"Bad --status {status!r}: expected one of {ALLOWED_STATUS}.",
            hint="--status enabled|disabled",
        )


def _config_summary(config: dict[str, Any]) -> str:
    """Short fingerprint of config keys for the human ls view."""
    keys = sorted(config.keys())
    if not keys:
        return "{}"
    return "{" + ", ".join(keys) + "}"


# --------------------------------------------------------------------------- #
# paw mcp list / ls
# --------------------------------------------------------------------------- #


@app.command("list")
def mcp_list(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List every MCP server configured by the authenticated persona.

    The backend returns a bare list of ``McpServerResponse`` rows
    keyed by UUID. Use ``paw mcp show <id>`` to drill into one.

    Examples:
      paw mcp list
      paw mcp list --json
      paw mcp list --plain
    """
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    servers = asyncio.run(_list_mcp_servers(state))

    if json_out:
        emit_json(servers)
        return
    if plain:
        emit_plain_rows(
            (
                s.get("id"),
                s.get("name"),
                s.get("status"),
                _config_summary(s.get("config") or {}),
            )
            for s in servers
        )
        return

    header = (
        f"{'ID':<{LS_ID_WIDTH}}  {'NAME':<{LS_NAME_WIDTH}}  {'STATUS':<{LS_STATUS_WIDTH}}  CONFIG"
    )
    emit_human(header)
    for s in servers:
        server_id = str(s.get("id", ""))[:LS_ID_WIDTH]
        name = str(s.get("name", ""))[:LS_NAME_WIDTH]
        status = str(s.get("status", ""))[:LS_STATUS_WIDTH]
        emit_human(
            f"{server_id:<{LS_ID_WIDTH}}  "
            f"{name:<{LS_NAME_WIDTH}}  "
            f"{status:<{LS_STATUS_WIDTH}}  "
            f"{_config_summary(s.get('config') or {})}"
        )


# `ls` alias for muscle memory with the other paw resources.
app.command("ls", help="Alias for `list`.")(mcp_list)


# --------------------------------------------------------------------------- #
# paw mcp show <id>
# --------------------------------------------------------------------------- #


@app.command("show")
def mcp_show(
    server_id: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch one MCP server by ID.

    The backend exposes no per-row GET endpoint; this finds the row
    in the list response client-side. Surfaces a 404-equivalent
    local error when the ID is not in the user's server list.

    Examples:
      paw mcp show 6c87...
      paw mcp show 6c87... --json
    """
    state = load_state(profile)
    servers = asyncio.run(_list_mcp_servers(state))
    match = next((s for s in servers if str(s.get("id")) == server_id), None)
    if match is None:
        raise LocalError(
            f"MCP server {server_id} not found.",
            hint="`paw mcp list` to see available IDs.",
        )

    if json_out:
        emit_json(match)
        return
    config_str = json.dumps(match.get("config") or {}, indent=2)
    emit_human(
        f"{match.get('id')}  {match.get('name')}\n"
        f"  status: {match.get('status')}\n"
        f"  config: {config_str}"
    )


# --------------------------------------------------------------------------- #
# paw mcp create
# --------------------------------------------------------------------------- #


@app.command("create")
def mcp_create(
    name: str = typer.Option(..., "--name", help="Display name (1-64 chars)."),
    config: str | None = typer.Option(
        None,
        "--config",
        help='Opaque JSON config forwarded to the bridge, e.g. \'{"command":"npx"}\'.',
    ),
    status: str = typer.Option("enabled", "--status", help="enabled | disabled (default enabled)."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Register a new MCP server for the authenticated persona.

    On success the response carries the freshly-issued ``id``;
    print it so callers can pipe it into subsequent verbs.

    Examples:
      paw mcp create --name notion --config '{"command":"npx","args":["@notionhq/mcp"]}'
      paw mcp create --name local --status disabled --json
    """
    _validate_status(status)
    config_dict = _parse_config(config)
    state = load_state(profile)
    server = asyncio.run(_create_mcp_server(state, name=name, config=config_dict, status=status))
    if json_out:
        emit_json(server)
        return
    emit_human(
        f"created mcp server {server.get('id')}\n"
        f"  name:   {server.get('name')}\n"
        f"  status: {server.get('status')}"
    )


# --------------------------------------------------------------------------- #
# paw mcp update <id>
# --------------------------------------------------------------------------- #


@app.command("update")
def mcp_update(
    server_id: str = typer.Argument(...),
    name: str | None = typer.Option(None, "--name", help="Replace display name."),
    config: str | None = typer.Option(
        None, "--config", help="Replace config JSON (full object, not a delta)."
    ),
    status: str | None = typer.Option(None, "--status", help="enabled | disabled."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Update an MCP server row.

    The backend's PATCH endpoint takes the same payload shape as
    create (``name`` + ``config`` + ``status``), so every field
    must be provided. ``paw mcp update`` fills any omitted flag
    from the current row before submitting so callers can mutate
    a single field without restating the rest.

    Examples:
      paw mcp update 6c87... --status disabled
      paw mcp update 6c87... --name "Notion (prod)" --json
    """
    _validate_status(status)
    if name is None and config is None and status is None:
        raise LocalError(
            "Provide at least one of --name, --config, --status.",
            hint="paw mcp update <id> --status disabled",
        )

    state = load_state(profile)
    current = asyncio.run(_get_mcp_server(state, server_id))
    body: dict[str, Any] = {
        "name": name if name is not None else current.get("name"),
        "config": _parse_config(config) if config is not None else current.get("config") or {},
        "status": status if status is not None else current.get("status"),
    }
    server = asyncio.run(_patch_mcp_server(state, server_id, body=body))
    if json_out:
        emit_json(server)
        return
    emit_human(
        f"updated {server_id}\n  name:   {server.get('name')}\n  status: {server.get('status')}"
    )


# --------------------------------------------------------------------------- #
# paw mcp delete <id>
# --------------------------------------------------------------------------- #


@app.command("delete")
def mcp_delete(
    server_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Delete an MCP server row. Idempotent on 404 (deleted=false).

    Examples:
      paw mcp delete 6c87... --yes
      paw mcp delete 6c87... --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm deletion.",
            hint="paw mcp delete <id> --yes",
        )
    state = load_state(profile)
    result = asyncio.run(_delete_mcp_server(state, server_id))
    if json_out:
        emit_json(result)
        return
    if result["deleted"]:
        emit_human(f"deleted {server_id}")
    else:
        emit_human(f"not found: {server_id}")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


async def _list_mcp_servers(state: PersonaState) -> list[dict[str, Any]]:
    """GET /api/v1/mcp/servers; backend returns a bare list of server rows."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/mcp/servers", expect=(200,))
    body = resp.json()
    if not isinstance(body, list):
        return []
    return [s for s in body if isinstance(s, dict)]


async def _get_mcp_server(state: PersonaState, server_id: str) -> dict[str, Any]:
    """Resolve one row by ID via the list endpoint (no per-row GET)."""
    servers = await _list_mcp_servers(state)
    match = next((s for s in servers if str(s.get("id")) == server_id), None)
    if match is None:
        raise LocalError(
            f"MCP server {server_id} not found.",
            hint="`paw mcp list` to see available IDs.",
        )
    return match


async def _create_mcp_server(
    state: PersonaState,
    *,
    name: str,
    config: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    """POST /api/v1/mcp/servers with the McpServerPayload body."""
    body: dict[str, Any] = {"name": name, "config": config, "status": status}
    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            "/api/v1/mcp/servers",
            json_body=body,
            expect=(200, 201),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _patch_mcp_server(
    state: PersonaState,
    server_id: str,
    *,
    body: dict[str, Any],
) -> dict[str, Any]:
    """PATCH /api/v1/mcp/servers/{id} with the full McpServerPayload body."""
    async with PawClient(state) as client:
        resp = await client.request(
            "PATCH",
            f"/api/v1/mcp/servers/{server_id}",
            json_body=body,
            expect=(200,),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _delete_mcp_server(state: PersonaState, server_id: str) -> dict[str, Any]:
    """DELETE /api/v1/mcp/servers/{id}; 404 -> deleted=false."""
    async with PawClient(state) as client:
        try:
            await client.request(
                "DELETE",
                f"/api/v1/mcp/servers/{server_id}",
                expect=(204,),
            )
        except ApiError as e:
            if e.status_code == HTTP_NOT_FOUND:
                return {"deleted": False, "reason": "not_found", "id": server_id}
            raise
    return {"deleted": True, "id": server_id}
