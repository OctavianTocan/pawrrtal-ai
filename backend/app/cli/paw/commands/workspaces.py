"""paw workspaces / workspace env / workspace files — resource CRUD + env + files.

Three logical groups share this module because they all resolve the same
``workspace_id`` (either explicit ``--workspace`` or the persona's default):

- ``paw workspaces ls / show / use / create / rename / delete`` — workspace
  rows themselves, hitting ``/api/v1/workspaces`` and its detail/CRUD routes.
- ``paw workspace env get / set / unset`` — per-workspace ``.env`` overrides
  via ``/api/v1/workspaces/{id}/env``.
- ``paw workspace files ls / cat / write / rm`` — file tree + content via
  ``/api/v1/workspaces/{id}/tree`` and ``/api/v1/workspaces/{id}/files/...``.

Output modes mirror ``paw conversations``: ``--json``, ``--plain``, default
human-readable. Exit codes come from ``app.cli.paw.errors``.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import typer

from app.cli.paw.config import PersonaState
from app.cli.paw.errors import ApiError, LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

# Column widths for the workspace ls table on an 80-col terminal: 36 char UUID,
# 30 char name, the remaining ~14 char fall to the IS_DEFAULT marker; path
# wraps at end-of-line because workspace paths frequently exceed 40 chars.
LS_ID_WIDTH = 36
LS_NAME_WIDTH = 30
LS_DEFAULT_WIDTH = 10

# Column widths for the models ls table.
MODELS_ID_WIDTH = 36
MODELS_NAME_WIDTH = 28
MODELS_HOST_WIDTH = 14

workspaces_app = typer.Typer(
    help="Manage workspaces (ls / show / use / create / rename / delete).",
    no_args_is_help=True,
)

workspace_app = typer.Typer(
    help="Per-workspace env vars and files (paw workspace env|files ...).",
    no_args_is_help=True,
)

env_app = typer.Typer(
    help="Per-workspace env overrides (get / set / unset).",
    no_args_is_help=True,
)

files_app = typer.Typer(
    help="Workspace file tree, read, write, delete.",
    no_args_is_help=True,
)

workspace_app.add_typer(env_app, name="env")
workspace_app.add_typer(files_app, name="files")


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _require_one_output_mode(*, json_out: bool, plain: bool) -> None:
    """Reject simultaneous --json + --plain. Mutually exclusive by design."""
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )


def _load_state(profile: str) -> PersonaState:
    """Load persona state for ``profile``; surface a friendly hint when absent."""
    try:
        return PersonaState.load(profile)
    except FileNotFoundError as e:
        raise LocalError(
            f"No persona state for profile {profile!r}.",
            hint="Run `paw login` first.",
        ) from e


def _resolve_workspace_id(state: PersonaState, override: str | None) -> str:
    """Pick the workspace ID to operate on; raise if neither override nor default set."""
    workspace_id = override or state.default_workspace_id
    if not workspace_id:
        raise LocalError(
            "No workspace selected.",
            hint="Pass --workspace ID or run `paw login` to capture a default.",
        )
    return workspace_id


def _stderr(message: str) -> None:
    """Write progress to stderr (keeps stdout clean for --json consumers)."""
    sys.stderr.write(message)
    if not message.endswith("\n"):
        sys.stderr.write("\n")
    sys.stderr.flush()


# --------------------------------------------------------------------------- #
# A. paw workspaces ...
# --------------------------------------------------------------------------- #


@workspaces_app.command("ls")
def workspaces_ls(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List the authenticated user's workspaces.

    Examples:
      paw workspaces ls
      paw workspaces ls --json
      paw workspaces ls --plain
    """
    _require_one_output_mode(json_out=json_out, plain=plain)
    state = _load_state(profile)
    workspaces = asyncio.run(_list_workspaces(state))

    if json_out:
        emit_json(workspaces)
        return
    if plain:
        emit_plain_rows(
            (w.get("id"), w.get("name"), w.get("path"), str(w.get("is_default", False)).lower())
            for w in workspaces
        )
        return

    header = (
        f"{'ID':<{LS_ID_WIDTH}}  {'NAME':<{LS_NAME_WIDTH}}  {'DEFAULT':<{LS_DEFAULT_WIDTH}}  PATH"
    )
    emit_human(header)
    for w in workspaces:
        emit_human(
            f"{w.get('id', '')!s:<{LS_ID_WIDTH}}  "
            f"{str(w.get('name', ''))[:LS_NAME_WIDTH]:<{LS_NAME_WIDTH}}  "
            f"{('yes' if w.get('is_default') else 'no'):<{LS_DEFAULT_WIDTH}}  "
            f"{w.get('path', '')}"
        )


@workspaces_app.command("show")
def workspaces_show(
    workspace: str | None = typer.Option(None, "--workspace", help="Workspace ID override."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Fetch a workspace by ID (defaults to the persona's default workspace).

    The backend exposes no per-row GET endpoint, so this finds the row in
    the list response client-side. Surfaces a 404-equivalent local error
    when the ID is not in the user's workspace list.

    Examples:
      paw workspaces show
      paw workspaces show --workspace ws-1 --json
    """
    state = _load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    workspaces = asyncio.run(_list_workspaces(state))
    match = next((w for w in workspaces if str(w.get("id")) == workspace_id), None)
    if match is None:
        raise LocalError(
            f"Workspace {workspace_id} not found.",
            hint="`paw workspaces ls` to see available IDs.",
        )

    if json_out:
        emit_json(match)
        return
    emit_human(
        f"{match.get('id')}  {match.get('name')}\n"
        f"  path:       {match.get('path')}\n"
        f"  is_default: {match.get('is_default')}\n"
        f"  slug:       {match.get('slug')}\n"
        f"  created_at: {match.get('created_at')}"
    )


@workspaces_app.command("use")
def workspaces_use(
    workspace_id: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Set the persona's default workspace ID for subsequent commands.

    Verifies the workspace exists by checking the user's list before
    persisting. The path is cached alongside the ID so other paw flows
    that need it (cookie scoping, future ``--workspace=current`` shortcuts)
    can read it without a second round-trip.

    Examples:
      paw workspaces use ws-1
      paw workspaces use 6c87... --json
    """
    state = _load_state(profile)
    workspaces = asyncio.run(_list_workspaces(state))
    match = next((w for w in workspaces if str(w.get("id")) == workspace_id), None)
    if match is None:
        raise LocalError(
            f"Workspace {workspace_id} not found.",
            hint="`paw workspaces ls` to see available IDs.",
        )

    state.default_workspace_id = workspace_id
    path = match.get("path")
    state.default_workspace_path = path if isinstance(path, str) else None
    state.save()

    payload = {"workspace_id": workspace_id, "path": state.default_workspace_path}
    if json_out:
        emit_json(payload)
        return
    emit_human(f"using workspace {workspace_id} ({state.default_workspace_path})")


@workspaces_app.command("create")
def workspaces_create(
    name: str = typer.Argument(..., help="Workspace name (1-120 chars)."),
    path: str | None = typer.Option(
        None,
        "--path",
        help="Absolute path under the configured workspace base dir; server picks one if omitted.",
    ),
    is_default: bool = typer.Option(
        False, "--default", help="Mark the new workspace as the user's default."
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create a new workspace.

    Examples:
      paw workspaces create "side-project"
      paw workspaces create "ops" --default --json
      paw workspaces create "exploration" --path /workspaces/exploration
    """
    state = _load_state(profile)
    workspace = asyncio.run(_create_workspace(state, name=name, path=path, is_default=is_default))
    if json_out:
        emit_json(workspace)
        return
    emit_human(
        f"created workspace {workspace.get('id')}\n"
        f"  name:       {workspace.get('name')}\n"
        f"  path:       {workspace.get('path')}\n"
        f"  is_default: {workspace.get('is_default')}"
    )


@workspaces_app.command("rename")
def workspaces_rename(
    workspace_id: str = typer.Argument(...),
    new_name: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Rename a workspace.

    Examples:
      paw workspaces rename ws-1 "Q2 planning"
      paw workspaces rename 6c87... "research" --json
    """
    state = _load_state(profile)
    workspace = asyncio.run(_patch_workspace(state, workspace_id, body={"name": new_name}))
    if json_out:
        emit_json(workspace)
        return
    emit_human(f"renamed {workspace_id} -> {workspace.get('name')}")


@workspaces_app.command("delete")
def workspaces_delete(
    workspace_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Delete a workspace. Idempotent on 404 (deleted=false); 409 exits 5.

    The backend refuses to delete a user's only workspace or the
    current default with 409 — surface that as an ApiError (exit 5)
    rather than treating it as a soft no-op.

    Examples:
      paw workspaces delete ws-old --yes
      paw workspaces delete 6c87... --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm deletion.",
            hint="paw workspaces delete <id> --yes",
        )
    state = _load_state(profile)
    result = asyncio.run(_delete_workspace(state, workspace_id))
    if json_out:
        emit_json(result)
        return
    if result["deleted"]:
        emit_human(f"deleted {workspace_id}")
    else:
        emit_human(f"not found: {workspace_id}")


async def _list_workspaces(state: PersonaState) -> list[dict[str, Any]]:
    """GET /api/v1/workspaces; return bare list."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/workspaces", expect=(200,))
    body = resp.json()
    return [w for w in body if isinstance(w, dict)] if isinstance(body, list) else []


async def _create_workspace(
    state: PersonaState,
    *,
    name: str,
    path: str | None,
    is_default: bool,
) -> dict[str, Any]:
    """POST /api/v1/workspaces with a WorkspaceCreate body."""
    body: dict[str, Any] = {"name": name, "is_default": is_default}
    if path is not None:
        body["path"] = path
    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            "/api/v1/workspaces",
            json_body=body,
            expect=(200, 201),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _patch_workspace(
    state: PersonaState,
    workspace_id: str,
    *,
    body: dict[str, Any],
) -> dict[str, Any]:
    """PATCH /api/v1/workspaces/{id} with the partial-update body."""
    async with PawClient(state) as client:
        resp = await client.request(
            "PATCH",
            f"/api/v1/workspaces/{workspace_id}",
            json_body=body,
            expect=(200,),
        )
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def _delete_workspace(state: PersonaState, workspace_id: str) -> dict[str, Any]:
    """DELETE /api/v1/workspaces/{id}; 404 returns deleted=false, 409 raises."""
    async with PawClient(state) as client:
        try:
            await client.request(
                "DELETE",
                f"/api/v1/workspaces/{workspace_id}",
                expect=(204,),
            )
        except ApiError as e:
            if "404" in e.message:
                return {"deleted": False, "reason": "not_found", "id": workspace_id}
            raise
    return {"deleted": True, "id": workspace_id}


# --------------------------------------------------------------------------- #
# B. paw workspace env ...
# --------------------------------------------------------------------------- #


@env_app.command("get")
def env_get(
    key: str | None = typer.Argument(None, help="Single env key to print; omit for full map."),
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Read workspace env overrides.

    Examples:
      paw workspace env get
      paw workspace env get GEMINI_API_KEY
      paw workspace env get --json
    """
    _require_one_output_mode(json_out=json_out, plain=plain)
    state = _load_state(profile)
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
    """Set one or more workspace env overrides.

    The PUT endpoint merges server-side: only the keys you pass are
    updated; existing ones not mentioned in the payload are preserved.

    Examples:
      paw workspace env set GEMINI_API_KEY=sk-...
      paw workspace env set EXA_API_KEY=... OPENAI_API_KEY=... --json
    """
    state = _load_state(profile)
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
    """Delete one or more workspace env overrides.

    Issues one DELETE per key and aggregates the results so callers
    see exactly which keys cleared and which were already absent.

    Examples:
      paw workspace env unset GEMINI_API_KEY --yes
      paw workspace env unset EXA_API_KEY OPENAI_API_KEY --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm.",
            hint="paw workspace env unset KEY --yes",
        )
    state = _load_state(profile)
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
        resp = await client.request(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/env",
            expect=(200,),
        )
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
                if "404" in e.message:
                    results.append({"key": key, "deleted": False, "reason": "not_found"})
                else:
                    raise
    return results


# --------------------------------------------------------------------------- #
# C. paw workspace files ...
# --------------------------------------------------------------------------- #


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
    """List workspace file tree (flat node list, filtered by ``path`` prefix).

    The backend's ``/tree`` endpoint returns the full recursive tree as a
    flat list. ``path`` is applied client-side as a prefix filter so
    ``paw workspace files ls memory`` returns only that subtree.

    Examples:
      paw workspace files ls
      paw workspace files ls memory --json
      paw workspace files ls notes --plain
    """
    _require_one_output_mode(json_out=json_out, plain=plain)
    state = _load_state(profile)
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
    """Print a workspace file's text content to stdout.

    Examples:
      paw workspace files cat memory/2026-05-06.md
      paw workspace files cat notes/todo.md --json
    """
    state = _load_state(profile)
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
    """Write content to a workspace file (creates parent directories).

    Provide content via ``--data 'literal'`` or ``--stdin`` (mutually
    exclusive). Stdin is the recommended path for content with shell
    metacharacters or newlines.

    Examples:
      paw workspace files write notes/todo.md -d "shop for milk"
      echo "hello" | paw workspace files write greet.md --stdin
    """
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

    state = _load_state(profile)
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
    """Delete a workspace file. Idempotent: 404 returns deleted=false.

    Examples:
      paw workspace files rm scratch/old.md --yes
      paw workspace files rm tmp/file --yes --json
    """
    if not yes:
        raise LocalError(
            "Pass --yes to confirm deletion.",
            hint="paw workspace files rm <path> --yes",
        )
    state = _load_state(profile)
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
            if "404" in e.message:
                return {"deleted": False, "reason": "not_found", "path": file_path}
            raise
    return {"deleted": True, "path": file_path}
