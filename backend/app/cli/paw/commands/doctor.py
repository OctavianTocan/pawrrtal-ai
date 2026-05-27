"""paw doctor — checklist of pre-flight checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
import typer

from app.cli.paw.config import PersonaState, cookies_path, profile_dir, state_path
from app.cli.paw.errors import AuthError, BackendUnreachable
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json

app = typer.Typer()


HTTP_OK = 200


@dataclass
class Check:
    """One row in the doctor checklist: name, pass/fail boolean, and detail."""

    name: str
    passed: bool
    detail: str = ""


@app.callback(invoke_without_command=True)
def doctor(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run a checklist of pre-flight checks. Exit 0 if all pass, 6 otherwise.

    Examples:
      paw doctor
      paw doctor --json
      paw doctor --profile staging
    """
    checks = asyncio.run(_run(profile))
    passed = all(c.passed for c in checks)

    if json_out:
        emit_json(
            {
                "passed": passed,
                "checks": [
                    {"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks
                ],
            }
        )
    else:
        lines = []
        for c in checks:
            mark = "OK" if c.passed else "FAIL"
            line = f"  [{mark}] {c.name}"
            if not c.passed and c.detail:
                line += f"   ({c.detail})"
            lines.append(line)
        lines.append("")
        lines.append(f"{sum(c.passed for c in checks)}/{len(checks)} passed.")
        emit_human("\n".join(lines))

    if not passed:
        raise typer.Exit(code=6)


async def _run(profile: str) -> list[Check]:
    checks: list[Check] = []
    checks.append(
        Check(
            "config_dir_exists",
            profile_dir(profile).exists(),
            detail=str(profile_dir(profile)),
        )
    )
    checks.append(
        Check(
            "state_file_exists",
            state_path(profile).exists(),
            detail=str(state_path(profile)),
        )
    )

    state: PersonaState | None = None
    try:
        state = PersonaState.load(profile)
        checks.append(Check("state_file_parseable", True))
    except Exception as e:
        checks.append(Check("state_file_parseable", False, detail=str(e)))
        return checks

    backend_reachable = False
    try:
        async with httpx.AsyncClient(base_url=state.api_base_url, timeout=5.0) as client:
            resp = await client.get("/api/v1/health")
            backend_reachable = resp.status_code == HTTP_OK
            checks.append(
                Check(
                    "backend_reachable",
                    backend_reachable,
                    detail=f"{state.api_base_url} -> {resp.status_code}",
                )
            )
    except httpx.ConnectError as e:
        checks.append(Check("backend_reachable", False, detail=str(e)))

    # Only verify the session token when we actually have one to check. A
    # fresh install (no state.json or no cookies on disk) skips this check —
    # paw login is the user's job to run first.
    if backend_reachable and cookies_path(profile).exists():
        await _append_token_valid_check(checks, state)
        await _append_models_endpoint_check(checks, state)

    return checks


async def _append_token_valid_check(checks: list[Check], state: PersonaState) -> None:
    """Probe /api/v1/users/me to confirm the persisted cookie still authenticates."""
    try:
        async with PawClient(state, timeout=5.0) as client:
            await client.request("GET", "/api/v1/users/me")
        checks.append(Check("token_valid", True))
    except AuthError:
        checks.append(Check("token_valid", False, detail="session expired; run paw login --force"))
    except BackendUnreachable as e:
        checks.append(Check("token_valid", False, detail=str(e.message)))


async def _append_models_endpoint_check(checks: list[Check], state: PersonaState) -> None:
    """Probe /api/v1/models to confirm at least one model is selectable.

    The catalog is filtered to hosts the user has credentials for, so an
    empty list means no provider keys are configured — paw send + chat
    will fail to dispatch until at least one key is set. Surfaces that
    state early under a single explicit check name.
    """
    try:
        async with PawClient(state, timeout=5.0) as client:
            resp = await client.request("GET", "/api/v1/models")
        body = resp.json()
        models = body.get("models") if isinstance(body, dict) else None
        count = len(models) if isinstance(models, list) else 0
        checks.append(
            Check(
                "models_endpoint_returns_nonempty",
                count > 0,
                detail=f"{count} model(s) available"
                if count > 0
                else "no models — configure a provider key",
            )
        )
    except AuthError:
        checks.append(
            Check("models_endpoint_returns_nonempty", False, detail="auth required"),
        )
    except BackendUnreachable as e:
        checks.append(
            Check("models_endpoint_returns_nonempty", False, detail=str(e.message)),
        )
