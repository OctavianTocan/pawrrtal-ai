"""paw login / logout — create or wipe the persona's session + cookies.

Auth flow notes (verified against backend/app/api/auth.py and backend/main.py):

- ``POST /auth/dev-login`` — dev-only convenience that signs in the seeded
  admin user. Returns 204 with a ``session_token`` cookie via fastapi-users.
- ``POST /auth/jwt/login`` — standard fastapi-users JWT login; form body
  ``username`` + ``password`` (OAuth2PasswordRequestForm).
- ``GET /api/v1/users/me`` — fastapi-users user info; canonical v1 mount.
  The legacy ``/users/me`` alias is kept on the server for frontend compat
  but new clients (paw) standardize on ``/api/v1/users``.
- Workspaces are seeded as a side-effect of ``PUT /api/v1/personalization``;
  there is no public POST endpoint for workspace creation. We call
  personalization with an empty profile (idempotent — workspace creation is
  guarded by ``ensure_default_workspace``) then GET ``/api/v1/workspaces``.
"""

from __future__ import annotations

import asyncio

import httpx
import typer

from typing import Any

from app.cli.paw.config import (
    ENV_BASE_URLS,
    PersonaState,
    cookies_path,
    profile_dir,
    state_path,
)
from app.cli.paw.errors import AuthError, BackendUnreachable, LocalError
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.output import emit_human, emit_json

LOGIN_TIMEOUT_SECONDS = 30.0
SUCCESS_STATUS_CODES = (200, 204)
ERROR_BODY_PREVIEW_CHARS = 200
SESSION_COOKIE_NAME = "session_token"

app = typer.Typer()


@app.command("login")
def login(
    env: str = typer.Option("local", "--env", help="Target environment: local/dev/stg/prod."),
    api: str | None = typer.Option(None, "--api", help="Backend base URL override."),
    profile: str = typer.Option("default", "--profile"),
    dev_admin: bool = typer.Option(
        False,
        "--dev-admin",
        help="Sign in as the dev-seeded admin via POST /auth/dev-login.",
    ),
    email: str | None = typer.Option(None, "--email"),
    password: str | None = typer.Option(None, "--password"),
    force: bool = typer.Option(False, "--force", help="Recreate state + cookies from scratch."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Sign in, ensure a workspace exists, persist state + cookies.

    Examples:
      paw login --dev-admin
      paw login --email tavi@example.com --password '...' --profile tavi
      paw login --env stg --dev-admin --json
    """
    if not dev_admin and not (email and password):
        raise LocalError(
            "Specify either --dev-admin or both --email and --password.",
            hint="paw login --dev-admin",
        )

    base_url = api or ENV_BASE_URLS.get(env)
    if not base_url:
        raise LocalError(
            f"Unknown env {env!r}.",
            hint=f"--env one of: {','.join(ENV_BASE_URLS)}",
        )

    result = asyncio.run(
        _do_login(
            env=env,
            base_url=base_url,
            profile=profile,
            dev_admin=dev_admin,
            email=email,
            password=password,
            force=force,
        )
    )
    if json_out:
        emit_json(result)
        return

    emit_human(
        f"paw logged in.\n"
        f"  profile:   {result['profile']}\n"
        f"  env:       {result['env']}\n"
        f"  api:       {result['api_base_url']}\n"
        f"  user:      {result['user_email']} ({result['user_id']})\n"
        f"  workspace: {result['default_workspace_id']}\n"
        f"  state:     {state_path(result['profile'])}\n"
        f"  cookies:   {cookies_path(result['profile'])}\n"
    )


async def _authenticate(
    client: httpx.AsyncClient,
    *,
    dev_admin: bool,
    email: str | None,
    password: str | None,
    base_url: str,
) -> None:
    """POST to the right auth endpoint and validate the cookie landed in the jar."""
    try:
        if dev_admin:
            resp = await client.post("/auth/dev-login")
        else:
            resp = await client.post(
                "/auth/jwt/login",
                data={"username": email, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.ConnectError as e:
        raise BackendUnreachable(
            f"Cannot reach backend at {base_url}: {e}",
        ) from e

    if resp.status_code not in SUCCESS_STATUS_CODES:
        raise AuthError(
            f"Login failed ({resp.status_code}): {resp.text[:ERROR_BODY_PREVIEW_CHARS]}",
            hint=(
                "If running with --dev-admin, ensure the backend is in dev mode "
                "with admin_email + admin_password configured."
            ),
        )


async def _ensure_default_workspace(client: httpx.AsyncClient) -> dict[str, Any]:
    """Return the persona's default workspace, seeding it via personalization if absent.

    The backend has no public POST /api/v1/workspaces endpoint; workspace creation is
    a side-effect of saving a personalization profile (`backend/app/api/personalization.py`).
    Sending an empty profile is safe — fields are all optional and the endpoint is
    idempotent against the workspace seed.
    """
    ws_list_resp = await client.get("/api/v1/workspaces")
    ws_list = ws_list_resp.json()

    default: dict[str, Any] | None = next(
        (w for w in ws_list if w.get("is_default")), None
    )
    if default is not None:
        return default

    seed_resp = await client.put("/api/v1/personalization", json={})
    if seed_resp.status_code not in SUCCESS_STATUS_CODES:
        raise AuthError(
            f"Workspace seed failed ({seed_resp.status_code}): "
            f"{seed_resp.text[:ERROR_BODY_PREVIEW_CHARS]}",
        )

    ws_list = (await client.get("/api/v1/workspaces")).json()
    default = next((w for w in ws_list if w.get("is_default")), None)
    if default is None and ws_list:
        default = ws_list[0]
    if default is None:
        raise AuthError(
            "Logged in but no workspace was provisioned by the backend.",
        )
    workspace: dict[str, Any] = default
    return workspace


async def _do_login(
    *,
    env: str,
    base_url: str,
    profile: str,
    dev_admin: bool,
    email: str | None,
    password: str | None,
    force: bool,
) -> dict[str, Any]:
    """Run the full login workflow and persist state + cookies on success."""
    if force:
        for p in (state_path(profile), cookies_path(profile)):
            if p.exists():
                p.unlink()

    profile_dir(profile).mkdir(parents=True, exist_ok=True)
    jar = load_cookies(cookies_path(profile))
    async with httpx.AsyncClient(
        base_url=base_url,
        cookies=jar,
        timeout=LOGIN_TIMEOUT_SECONDS,
        follow_redirects=False,
    ) as client:
        await _authenticate(
            client,
            dev_admin=dev_admin,
            email=email,
            password=password,
            base_url=base_url,
        )

        if SESSION_COOKIE_NAME not in {c.name for c in jar}:
            raise AuthError(
                f"Login succeeded but no {SESSION_COOKIE_NAME} cookie was set.",
            )

        me = (await client.get("/api/v1/users/me")).json()
        workspace = await _ensure_default_workspace(client)

    save_cookies(jar, cookies_path(profile))
    state = PersonaState(
        profile=profile,
        env=env,
        api_base_url=base_url,
        user_id=str(me["id"]),
        user_email=me["email"],
        default_workspace_id=str(workspace["id"]),
        default_workspace_path=workspace.get("path"),
    )
    state.save()
    return {
        "profile": state.profile,
        "env": state.env,
        "api_base_url": state.api_base_url,
        "user_id": state.user_id,
        "user_email": state.user_email,
        "default_workspace_id": state.default_workspace_id,
        "default_workspace_path": state.default_workspace_path,
        "state_file": str(state_path(profile)),
        "cookies_file": str(cookies_path(profile)),
    }


@app.command("logout")
def logout(
    profile: str = typer.Option("default", "--profile"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Forget the persona's session + cookies. Local-only; does not call /auth/logout.

    Examples:
      paw logout --yes
      paw logout --profile staging --yes
    """
    sp = state_path(profile)
    cp = cookies_path(profile)
    if not sp.exists() and not cp.exists():
        if json_out:
            emit_json({"deleted": False, "reason": "not_initialized"})
        else:
            emit_human("Nothing to do.")
        return
    if not yes:
        raise typer.BadParameter("Pass --yes to confirm logout (deletes local state + cookies).")
    if sp.exists():
        sp.unlink()
    if cp.exists():
        cp.unlink()
    if json_out:
        emit_json({"deleted": True, "profile": profile})
    else:
        emit_human(f"Logged out (profile={profile}).")
