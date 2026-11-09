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
from typing import Any

import typer

from app.cli.paw.commands.workspace_env_files import env_app, files_app
from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import ApiError, LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

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

# Mirrors HTTPStatus.NOT_FOUND. Local constant so the few "is this a 404
# we should swallow?" sites read self-evidently without importing http.
HTTP_NOT_FOUND = 404

workspaces_app = typer.Typer(
    help="Manage workspaces (ls / show / use / create / rename / delete).",
    no_args_is_help=True,
)

workspace_app = typer.Typer(
    help="Per-workspace env vars and files (paw workspace env|files ...).",
    no_args_is_help=True,
)

workspace_app.add_typer(env_app, name="env")
workspace_app.add_typer(files_app, name="files")


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _resolve_workspace_id(state: PersonaState, override: str | None) -> str:
    """Pick the workspace ID to operate on; raise if neither override nor default set."""
    workspace_id = override or state.default_workspace_id
    if not workspace_id:
        raise LocalError(
            "No workspace selected.",
            hint="Pass --workspace ID or run `paw login` to capture a default.",
        )
    return workspace_id


@workspace_app.command("status")
def workspace_status(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show whether onboarding has a default workspace ready."""
    state = load_state(profile)
    payload = asyncio.run(_get_onboarding_status(state))
    if json_out:
        emit_json(payload)
        return
    workspace = payload.get("workspace") if isinstance(payload, dict) else None
    workspace_id = workspace.get("id") if isinstance(workspace, dict) else "-"
    emit_human(
        f"ready: {'yes' if payload.get('has_workspace_ready') else 'no'}\nworkspace: {workspace_id}"
    )


@workspace_app.command("skills")
def workspace_skills(
    workspace: str | None = typer.Option(None, "--workspace"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List skills available in a workspace."""
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    workspace_id = _resolve_workspace_id(state, workspace)
    skills = asyncio.run(_list_workspace_skills(state, workspace_id))
    if json_out:
        emit_json(skills)
        return
    if plain:
        emit_plain_rows(
            (skill.get("name"), skill.get("trigger"), skill.get("has_skill_md")) for skill in skills
        )
        return
    if not skills:
        emit_human("No workspace skills found.")
        return
    for skill in skills:
        suffix = "" if skill.get("has_skill_md") else " (missing SKILL.md)"
        emit_human(f"{skill.get('name')}: {skill.get('summary')}{suffix}")


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
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
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
    state = load_state(profile)
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
    state = load_state(profile)
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
    state = load_state(profile)
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
    state = load_state(profile)
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
    state = load_state(profile)
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
            if e.status_code == HTTP_NOT_FOUND:
                return {"deleted": False, "reason": "not_found", "id": workspace_id}
            raise
    return {"deleted": True, "id": workspace_id}


async def _get_onboarding_status(state: PersonaState) -> dict[str, Any]:
    """GET /api/v1/workspaces/onboarding-status."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/workspaces/onboarding-status", expect=(200,))
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def _list_workspace_skills(state: PersonaState, workspace_id: str) -> list[dict[str, Any]]:
    """GET /api/v1/workspaces/{id}/skills."""
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/skills",
            expect=(200,),
        )
    body = resp.json()
    return [skill for skill in body if isinstance(skill, dict)] if isinstance(body, list) else []
