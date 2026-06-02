"""paw projects — project CRUD.

Projects are lightweight conversation grouping records. The backend exposes
list/create/rename/delete, so this command mirrors that surface without adding
client-only behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState, load_state
from app.cli.paw.errors import ApiError, LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

HTTP_NOT_FOUND = 404
PROJECT_ID_WIDTH = 36
PROJECT_NAME_WIDTH = 32

app = typer.Typer(
    help="Manage projects (conversation grouping).",
    no_args_is_help=True,
)


@app.command("ls")
def projects_ls(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List projects owned by the authenticated persona."""
    require_one_output_mode(json_out=json_out, plain=plain)
    state = load_state(profile)
    projects = asyncio.run(_list_projects(state))

    if json_out:
        emit_json(projects)
        return
    if plain:
        emit_plain_rows(
            (project.get("id"), project.get("name"), project.get("updated_at"))
            for project in projects
        )
        return

    emit_human(f"{'ID':<{PROJECT_ID_WIDTH}}  {'NAME':<{PROJECT_NAME_WIDTH}}  UPDATED")
    for project in projects:
        project_id = str(project.get("id", ""))[:PROJECT_ID_WIDTH]
        name = str(project.get("name", ""))[:PROJECT_NAME_WIDTH]
        emit_human(
            f"{project_id:<{PROJECT_ID_WIDTH}}  "
            f"{name:<{PROJECT_NAME_WIDTH}}  "
            f"{project.get('updated_at', '')}"
        )


app.command("list", help="Alias for `ls`.")(projects_ls)


@app.command("create")
def projects_create(
    name: str = typer.Argument(..., help="Project name."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Create a project."""
    state = load_state(profile)
    project = asyncio.run(_create_project(state, name=name))
    if json_out:
        emit_json(project)
        return
    emit_human(f"created project {project.get('id')}: {project.get('name')}")


@app.command("rename")
def projects_rename(
    project_id: str = typer.Argument(...),
    name: str = typer.Argument(..., help="New project name."),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Rename a project."""
    state = load_state(profile)
    project = asyncio.run(_rename_project(state, project_id=project_id, name=name))
    if json_out:
        emit_json(project)
        return
    emit_human(f"renamed project {project_id}: {project.get('name')}")


@app.command("delete")
def projects_delete(
    project_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Delete a project. Linked conversations are unlinked, not deleted."""
    if not yes:
        raise LocalError(
            "Pass --yes to confirm deletion.",
            hint="paw projects delete <id> --yes",
        )
    state = load_state(profile)
    result = asyncio.run(_delete_project(state, project_id))
    if json_out:
        emit_json(result)
        return
    emit_human(f"deleted {project_id}" if result["deleted"] else f"not found: {project_id}")


async def _list_projects(state: PersonaState) -> list[dict[str, Any]]:
    """GET /api/v1/projects."""
    async with PawClient(state) as client:
        resp = await client.request("GET", "/api/v1/projects", expect=(200,))
    body = resp.json()
    return (
        [project for project in body if isinstance(project, dict)] if isinstance(body, list) else []
    )


async def _create_project(state: PersonaState, *, name: str) -> dict[str, Any]:
    """POST /api/v1/projects."""
    async with PawClient(state) as client:
        resp = await client.request(
            "POST",
            "/api/v1/projects",
            json_body={"name": name},
            expect=(201,),
        )
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def _rename_project(state: PersonaState, *, project_id: str, name: str) -> dict[str, Any]:
    """PATCH /api/v1/projects/{id}."""
    async with PawClient(state) as client:
        resp = await client.request(
            "PATCH",
            f"/api/v1/projects/{project_id}",
            json_body={"name": name},
            expect=(200,),
        )
    body = resp.json()
    return body if isinstance(body, dict) else {}


async def _delete_project(state: PersonaState, project_id: str) -> dict[str, Any]:
    """DELETE /api/v1/projects/{id}; 404 returns deleted=false."""
    async with PawClient(state) as client:
        try:
            await client.request("DELETE", f"/api/v1/projects/{project_id}", expect=(204,))
        except ApiError as e:
            if e.status_code == HTTP_NOT_FOUND:
                return {"deleted": False, "reason": "not_found", "project_id": project_id}
            raise
    return {"deleted": True, "project_id": project_id}
