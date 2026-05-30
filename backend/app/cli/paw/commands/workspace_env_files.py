"""`paw workspace env` and `paw workspace files` command groups."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import ApiError, LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

HTTP_NOT_FOUND = 404

env_app = typer.Typer(
    help="Per-workspace env overrides (get / set / unset).",
    no_args_is_help=True,
)

files_app = typer.Typer(
    help="Workspace file tree, read, write, delete.",
    no_args_is_help=True,
)


def _resolve_workspace_id(state: PersonaState, override: str | None) -> str:
    """Pick the workspace ID to operate on; raise if neither override nor default set."""
    workspace_id = override or state.default_workspace_id
    if not workspace_id:
        raise LocalError(
            "No workspace selected.",
            hint="Pass --workspace ID or run `paw login` to capture a default.",
        )
    return workspace_id


@env_app.command("get")
def env_get(
    key: str | None = typer.Argument(None, help="Single env key to print; omit for full map."),
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Read workspace env overrides."""
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    envelope = asyncio.run(_get_workspace_env(state, workspace_id))
    vars_dict = envelope.get("vars", {}) if isinstance(envelope, dict) else {}

    if key is not None:
        value = vars_dict.get(key, "")
        if json_out:
            emit_json({key: value})
            return
        emit_human(value)
        return

    if json_out:
        emit_json(vars_dict)
        return
    if plain:
        emit_plain_rows((k, v) for k, v in vars_dict.items())
        return
    for k, v in vars_dict.items():
        emit_human(f"{k}={v}")


@env_app.command("set")
def env_set(
    pairs: list[str] = typer.Argument(..., help="One or more KEY=VALUE pairs."),
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Set one or more workspace env overrides."""
    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    deltas = _parse_kv_pairs(pairs)
    envelope = asyncio.run(_put_workspace_env(state, workspace_id, vars_dict=deltas))
    vars_dict = envelope.get("vars", {}) if isinstance(envelope, dict) else {}
    if json_out:
        emit_json(vars_dict)
        return
    emit_human(f"set {len(deltas)} key(s): {', '.join(sorted(deltas))}")


@env_app.command("unset")
def env_unset(
    keys: list[str] = typer.Argument(..., help="One or more env keys to clear."),
    workspace: str | None = typer.Option(None, "--workspace"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Delete one or more workspace env overrides."""
    if not yes:
        raise LocalError(
            "Pass --yes to confirm.",
            hint="paw workspace env unset KEY --yes",
        )
    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    results = asyncio.run(_delete_workspace_env_keys(state, workspace_id, keys))
    if json_out:
        emit_json(results)
        return
    for entry in results:
        status_label = "ok" if entry["deleted"] else f"skipped ({entry.get('reason', '?')})"
        emit_human(f"{entry['key']}: {status_label}")


def _parse_kv_pairs(pairs: list[str]) -> dict[str, str]:
    """Parse ``KEY=VALUE`` strings into a dict; reject malformed entries early."""
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise LocalError(
                f"Bad pair {raw!r}: expected KEY=VALUE.",
                hint="paw workspace env set FOO=bar BAZ=qux",
            )
        key, _, value = raw.partition("=")
        if not key:
            raise LocalError(f"Bad pair {raw!r}: empty key.")
        out[key] = value
    return out


async def _get_workspace_env(state: PersonaState, workspace_id: str) -> dict[str, Any]:
    """GET /api/v1/workspaces/{id}/env -> ``{vars: {...}}`` envelope."""
    async with PawClient(state) as client:
        resp = await client.request("GET", f"/api/v1/workspaces/{workspace_id}/env", expect=(200,))
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _put_workspace_env(
    state: PersonaState,
    workspace_id: str,
    *,
    vars_dict: dict[str, str],
) -> dict[str, Any]:
    """PUT /api/v1/workspaces/{id}/env with the merge-style delta payload."""
    async with PawClient(state) as client:
        resp = await client.request(
            "PUT",
            f"/api/v1/workspaces/{workspace_id}/env",
            json_body={"vars": vars_dict},
            expect=(200,),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _delete_workspace_env_keys(
    state: PersonaState,
    workspace_id: str,
    keys: list[str],
) -> list[dict[str, Any]]:
    """Issue one DELETE per key, treating 404 as a soft no-op."""
    results: list[dict[str, Any]] = []
    async with PawClient(state) as client:
        for key in keys:
            try:
                await client.request(
                    "DELETE",
                    f"/api/v1/workspaces/{workspace_id}/env/{key}",
                    expect=(204,),
                )
                results.append({"key": key, "deleted": True})
            except ApiError as e:
                if e.status_code == HTTP_NOT_FOUND:
                    results.append({"key": key, "deleted": False, "reason": "not_found"})
                else:
                    raise
    return results


@files_app.command("ls")
def files_ls(
    path: str = typer.Argument(
        "",
        help="Workspace-relative path prefix to filter the flat tree (empty = all).",
    ),
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List workspace file tree (flat node list, filtered by ``path`` prefix)."""
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    envelope = asyncio.run(_get_workspace_tree(state, workspace_id))
    nodes = envelope.get("nodes", []) if isinstance(envelope, dict) else []
    if isinstance(path, str) and path:
        nodes = [
            n for n in nodes if isinstance(n, dict) and str(n.get("path", "")).startswith(path)
        ]

    if json_out:
        emit_json(nodes)
        return
    if plain:
        emit_plain_rows(
            (n.get("path"), "dir" if n.get("is_dir") else "file", n.get("size") or "")
            for n in nodes
            if isinstance(n, dict)
        )
        return
    for n in nodes:
        if not isinstance(n, dict):
            continue
        kind = "d" if n.get("is_dir") else "f"
        size = n.get("size")
        size_str = f"{size:>8}" if isinstance(size, int) else "       -"
        emit_human(f"{kind}  {size_str}  {n.get('path', '')}")


@files_app.command("cat")
def files_cat(
    path: str = typer.Argument(..., help="Workspace-relative file path."),
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Print a workspace file's text content to stdout."""
    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    envelope = asyncio.run(_read_workspace_file(state, workspace_id, path))
    if json_out:
        emit_json(envelope)
        return
    content = envelope.get("content", "") if isinstance(envelope, dict) else ""
    sys.stdout.write(content)
    sys.stdout.flush()


@files_app.command("write")
def files_write(
    path: str = typer.Argument(..., help="Workspace-relative file path."),
    content: str | None = typer.Option(None, "-d", "--data", help="Inline content."),
    use_stdin: bool = typer.Option(False, "--stdin", help="Read file content from stdin."),
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Write content to a workspace file (creates parent directories)."""
    if use_stdin and content is not None:
        raise LocalError(
            "Pass --stdin or --data, not both.",
            hint="--stdin reads content from stdin.",
        )
    if not use_stdin and content is None:
        raise LocalError(
            "Provide --stdin or --data CONTENT.",
            hint="paw workspace files write path/file -d 'text'",
        )
    payload_body = sys.stdin.read() if use_stdin else (content or "")

    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    envelope = asyncio.run(_write_workspace_file(state, workspace_id, path, payload_body))
    if json_out:
        emit_json(envelope)
        return
    emit_human(f"wrote {path} ({len(payload_body)} chars)")


@files_app.command("rm")
def files_rm(
    path: str = typer.Argument(..., help="Workspace-relative file path."),
    yes: bool = typer.Option(False, "--yes", "-y"),
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Delete a workspace file. Idempotent: 404 returns deleted=false."""
    if not yes:
        raise LocalError(
            "Pass --yes to confirm deletion.",
            hint="paw workspace files rm <path> --yes",
        )
    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    result = asyncio.run(_delete_workspace_file(state, workspace_id, path))
    if json_out:
        emit_json(result)
        return
    if result["deleted"]:
        emit_human(f"deleted {path}")
    else:
        emit_human(f"not found: {path}")


async def _get_workspace_tree(state: PersonaState, workspace_id: str) -> dict[str, Any]:
    """GET /api/v1/workspaces/{id}/tree -> {workspace_id, nodes:[...]}."""
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/tree",
            expect=(200,),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _read_workspace_file(
    state: PersonaState,
    workspace_id: str,
    file_path: str,
) -> dict[str, Any]:
    """GET /api/v1/workspaces/{id}/files/{path} -> {path, content}."""
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/files/{file_path}",
            expect=(200,),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _write_workspace_file(
    state: PersonaState,
    workspace_id: str,
    file_path: str,
    content: str,
) -> dict[str, Any]:
    """PUT /api/v1/workspaces/{id}/files/{path} with the content body."""
    async with PawClient(state) as client:
        resp = await client.request(
            "PUT",
            f"/api/v1/workspaces/{workspace_id}/files/{file_path}",
            json_body={"content": content},
            expect=(200,),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _delete_workspace_file(
    state: PersonaState,
    workspace_id: str,
    file_path: str,
) -> dict[str, Any]:
    """DELETE /api/v1/workspaces/{id}/files/{path}; 404 -> deleted=false."""
    async with PawClient(state) as client:
        try:
            await client.request(
                "DELETE",
                f"/api/v1/workspaces/{workspace_id}/files/{file_path}",
                expect=(204,),
            )
        except ApiError as e:
            if e.status_code == HTTP_NOT_FOUND:
                return {"deleted": False, "reason": "not_found", "path": file_path}
            raise
    return {"deleted": True, "path": file_path}
