"""paw auth status — confirm we're logged in and who we are."""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState, state_path
from app.cli.paw.errors import AuthError, BackendUnreachableError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

app = typer.Typer()


@app.command("status")
def status(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show whether paw thinks it's authenticated. Validates by calling /api/v1/users/me.

    Exit codes: 0 authenticated, 3 not.

    Examples:
      paw auth status
      paw auth status --json
    """
    sp = state_path(profile)
    if not sp.exists():
        if json_out:
            emit_json(
                {
                    "authenticated": False,
                    "profile": profile,
                    "hint": "Run `paw login`.",
                }
            )
        else:
            emit_human("Not authenticated. Run `paw login`.")
        raise typer.Exit(code=3)

    state = PersonaState.load(profile)
    try:
        out = asyncio.run(_verify(state))
    except (AuthError, BackendUnreachableError) as e:
        if json_out:
            emit_json(
                {
                    "authenticated": False,
                    "profile": profile,
                    "error": e.message,
                    "hint": e.hint,
                }
            )
        else:
            emit_human(f"Session invalid: {e.message}\n  Hint: paw login --force")
        raise typer.Exit(code=3) from e

    out.update(
        {
            "authenticated": True,
            "profile": state.profile,
            "state_file": str(state_path(profile)),
        }
    )
    if json_out:
        emit_json(out)
        return

    emit_human(
        f"Authenticated as {out['user_email']} ({out['user_id']})\n"
        f"  profile:   {out['profile']}\n"
        f"  env:       {out['env']}\n"
        f"  api:       {out['api_base_url']}\n"
        f"  workspace: {out['default_workspace_id']}\n"
    )


async def _verify(state: PersonaState) -> dict[str, Any]:
    """Hit /api/v1/users/me with the persona's cookie jar; raises AuthError on 401."""
    async with PawClient(state) as client:
        me = (await client.request("GET", "/api/v1/users/me")).json()
    return {
        "user_email": me["email"],
        "user_id": me["id"],
        "env": state.env,
        "api_base_url": state.api_base_url,
        "default_workspace_id": state.default_workspace_id,
    }
