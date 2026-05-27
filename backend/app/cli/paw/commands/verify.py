"""paw verify — end-to-end provider verification scenarios.

Each subcommand drives the real chat surface against a backend (mocked
under test, live in CI / dev). Scenarios assert on observable state
exclusively, never internal state — so the same suite catches both
backend regressions and protocol drift between the CLI and the API.

Exit codes match the rest of the paw surface:

- 0 success (every check passed)
- 3/4/5 auth / unreachable / API error (raised by ``PawClient``)
- 6 verification failed — at least one check is ``passed=False``

Use ``--json`` for machine-readable output suitable for piping into
``jq``; the human renderer is the default and prints one OK/FAIL line
per check.
"""

from __future__ import annotations

import asyncio

import typer

from app.cli.paw.config import PersonaState
from app.cli.paw.errors import LocalError, VerificationFailed
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json
from app.cli.paw.verify.codex import SCENARIO_HTTP_TIMEOUT_SECONDS, run_codex_scenario
from app.cli.paw.verify.scenarios import ScenarioResult

app = typer.Typer(
    help="End-to-end provider verification scenarios.",
    no_args_is_help=True,
)


@app.command("codex")
def verify_codex(
    profile: str = typer.Option("default", "--profile"),
    keep_conversation: bool = typer.Option(
        False,
        "--keep-conversation",
        help="Skip the cleanup DELETE so the conversation row survives the run.",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run the Codex provider E2E scenario.

    Exits 6 if any check fails. ``--json`` dumps the full payload + artifacts
    for diagnosis (events, durations, response bodies).

    Examples:
      paw verify codex
      paw verify codex --json | jq '.checks[] | select(.passed == false)'
      paw verify codex --keep-conversation
    """
    state = _load_state(profile)
    result = asyncio.run(_run_scenario(state, keep_conversation=keep_conversation))
    if json_out:
        emit_json(result.to_dict())
    else:
        emit_human(_render(result))
    if not result.passed:
        failed_names = ", ".join(c.name for c in result.checks if not c.passed)
        raise VerificationFailed(f"codex scenario failed ({failed_names})")


def _load_state(profile: str) -> PersonaState:
    """Load persona state or raise a paw ``LocalError`` if missing."""
    try:
        return PersonaState.load(profile)
    except FileNotFoundError as e:
        raise LocalError(
            f"No persona state for profile {profile!r}.",
            hint="Run `paw login` first.",
        ) from e


async def _run_scenario(state: PersonaState, *, keep_conversation: bool) -> ScenarioResult:
    """Open one ``PawClient`` for the whole scenario and dispatch."""
    async with PawClient(state, timeout=SCENARIO_HTTP_TIMEOUT_SECONDS) as client:
        return await run_codex_scenario(state, client, keep_conversation=keep_conversation)


def _render(r: ScenarioResult) -> str:
    """Render a scenario result as one OK/FAIL line per check."""
    lines = [f"scenario: {r.name}  passed={r.passed}"]
    for c in r.checks:
        mark = "OK" if c.passed else "FAIL"
        line = f"  [{mark}] {c.name}"
        if not c.passed and c.detail:
            line += f"   ({c.detail})"
        lines.append(line)
    return "\n".join(lines) + "\n"
