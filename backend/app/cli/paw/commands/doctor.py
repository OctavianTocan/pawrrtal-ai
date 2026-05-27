"""paw doctor — checklist of pre-flight checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
import typer

from ..config import PersonaState, profile_dir, state_path
from ..output import emit_human, emit_json

app = typer.Typer()


@dataclass
class Check:
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

    try:
        async with httpx.AsyncClient(base_url=state.api_base_url, timeout=5.0) as client:
            resp = await client.get("/api/v1/health")
            checks.append(
                Check(
                    "backend_reachable",
                    resp.status_code == 200,
                    detail=f"{state.api_base_url} -> {resp.status_code}",
                )
            )
    except httpx.ConnectError as e:
        checks.append(Check("backend_reachable", False, detail=str(e)))

    return checks
