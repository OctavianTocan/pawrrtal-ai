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
from collections.abc import Awaitable, Callable

import typer

from app.cli.paw.commands.verify_lazy import (
    run_all_providers_scenario,
    run_chat_roundtrip_scenario,
    run_codex_scenario,
    run_cost_scenario,
    run_google_chat_scenario,
    run_lcm_scenario,
    run_model_switch_scenario,
    run_telegram_scenario,
)
from app.cli.paw.commands.verify_output import emit_and_exit, emit_many_and_exit, emit_runtime_error
from app.cli.paw.config import PersonaState
from app.cli.paw.errors import LocalError, PawError
from app.cli.paw.http import PawClient
from app.cli.paw.verify.scenarios import ScenarioResult

# Canonical order all-dispatcher walks when no --include flag narrows it.
# Order matters: codex first because its credentials are most likely to be
# unconfigured (early skip-or-fail surfaces the diagnosis); chat-roundtrip
# next so the stream-vs-DB invariant is asserted before the multi-turn
# switch scenario muddies the row. ``telegram`` and ``cost`` run last:
# they touch a different resource family (channels / cost ledger) and
# never depend on a chat completing — so a Codex/chat outage doesn't
# mask a channels regression, and cost runs after the others have already
# accumulated some ledger rows on the same backend. ``lcm`` slots after
# ``cost`` because it depends on chat completing (same as ``cost``) but
# only asserts on the read-only LCM debug endpoint — running last keeps
# the chat-dependent suites grouped together.
DEFAULT_SUITES = (
    "codex",
    "chat-roundtrip",
    "model-switch",
    "telegram",
    "google-chat",
    "cost",
    "lcm",
)
SCENARIO_HTTP_TIMEOUT_SECONDS = 120.0

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
    result = _run_one_command(
        state,
        lambda client: run_codex_scenario(
            state,
            client,
            keep_conversation=keep_conversation,
        ),
        json_out=json_out,
        label="codex",
    )
    emit_and_exit(result, json_out=json_out, label="codex")


@app.command("chat-roundtrip")
def verify_chat_roundtrip(
    profile: str = typer.Option("default", "--profile"),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override the model id (defaults to the first catalog model).",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Compare one streamed turn's SSE events against the persisted DB row.

    Catches the "stream looked right but the DB row is wrong" bug class —
    content drift, dropped tool_use rows, thinking-render regressions.

    Examples:
      paw verify chat-roundtrip
      paw verify chat-roundtrip --model openai-codex:openai/gpt-5.5 --json
    """
    state = _load_state(profile)
    result = _run_one_command(
        state,
        lambda client: run_chat_roundtrip_scenario(
            state,
            client,
            model_override=model,
        ),
        json_out=json_out,
        label="chat-roundtrip",
    )
    emit_and_exit(result, json_out=json_out, label="chat-roundtrip")


@app.command("model-switch")
def verify_model_switch(
    profile: str = typer.Option("default", "--profile"),
    from_model: str | None = typer.Option(
        None,
        "--from",
        help="Starting model id (defaults to the first catalog model).",
    ),
    to_model: str | None = typer.Option(
        None,
        "--to",
        help="Model id to switch to (defaults to the next distinct catalog model).",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Switch models mid-conversation and assert row + state-machine integrity.

    Verifies migration 012's model_id canonicalisation and migration 020's
    ``reasoning_effort`` CHECK constraint via the PATCH path.

    Examples:
      paw verify model-switch
      paw verify model-switch --from openai-codex:openai/gpt-5.5 --to claude-code-pty:anthropic/claude-opus-4-7
    """
    state = _load_state(profile)
    result = _run_one_command(
        state,
        lambda client: run_model_switch_scenario(
            state,
            client,
            from_override=from_model,
            to_override=to_model,
        ),
        json_out=json_out,
        label="model-switch",
    )
    emit_and_exit(result, json_out=json_out, label="model-switch")


@app.command("telegram")
def verify_telegram(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Verify Telegram channel configuration, simulation, and diagnostics.

    Lists bindings, issues a fresh link code, feeds ``/status`` through
    ``/api/v1/channels/telegram/simulate`` for the authenticated user's
    existing binding, and checks the diagnostics endpoint. It does not
    unlink or modify an existing Telegram binding.

    Exits 6 if any check fails. ``--json`` dumps the full payload and
    artifacts needed to diagnose the failed step.

    Examples:
      paw verify telegram
      paw verify telegram --json | jq '.checks[] | select(.passed == false)'
    """
    state = _load_state(profile)
    result = _run_one_command(
        state,
        lambda client: run_telegram_scenario(state, client),
        json_out=json_out,
        label="telegram",
    )
    emit_and_exit(result, json_out=json_out, label="telegram")


@app.command("google-chat")
def verify_google_chat(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Verify the Google Chat channel's formatting, command parsing, and registration.

    The channel has no HTTP surface (Pub/Sub in, Chat REST out), so after a
    backend health ping this asserts the channel's pure logic — Markdown→Chat
    formatting (the markup-leak guard), slash-command parsing of the add-on
    event shape, inbound field extraction — plus registration. The full live
    Pub/Sub→Chat round-trip is bot-covered; see the
    ``live_pubsub_roundtrip_bot_covered`` marker check.

    Examples:
      paw verify google-chat
      paw verify google-chat --json | jq '.checks[] | select(.passed == false)'
    """
    state = _load_state(profile)
    result = _run_one_command(
        state,
        lambda client: run_google_chat_scenario(state, client),
        json_out=json_out,
        label="google-chat",
    )
    emit_and_exit(result, json_out=json_out, label="google-chat")


@app.command("cost")
def verify_cost(
    profile: str = typer.Option("default", "--profile"),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override the model id (defaults to the first catalog model).",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Send one chat turn and assert the cost summary + ledger accumulated.

    Baselines the cost surface, drives one chat turn, then asserts the
    summary ``current_usd`` strictly increased and a new ledger row
    references the new conversation with a non-zero ``cost_usd``. The
    per-user budget *limit* is configured via env, not a setter
    endpoint; the scenario records that gap as the passing
    ``budget_endpoint_unavailable`` check.

    Examples:
      paw verify cost
      paw verify cost --json | jq '.checks[] | select(.passed == false)'
    """
    state = _load_state(profile)
    result = _run_one_command(
        state,
        lambda client: run_cost_scenario(state, client, model_override=model),
        json_out=json_out,
        label="cost",
    )
    emit_and_exit(result, json_out=json_out, label="cost")


@app.command("lcm")
def verify_lcm(
    profile: str = typer.Option("default", "--profile"),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override the model id (defaults to the first catalog model).",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Drive two chat turns and assert LCM observability for the conversation.

    Sends two turns through the real chat surface, then asserts the LCM
    debug endpoint (``GET /api/v1/lcm/conversations/{id}/context``)
    returns a 200 with the expected envelope. Does NOT assert active
    recall (memory seed -> dream -> recall) — see the
    ``memory_seeding_endpoint_unavailable`` and
    ``dreaming_trigger_endpoint_unavailable`` marker checks.

    Examples:
      paw verify lcm
      paw verify lcm --json | jq '.checks[] | select(.passed == false)'
    """
    state = _load_state(profile)
    result = _run_one_command(
        state,
        lambda client: run_lcm_scenario(state, client, model=model),
        json_out=json_out,
        label="lcm",
    )
    emit_and_exit(result, json_out=json_out, label="lcm")


@app.command("all-providers")
def verify_all_providers(
    profile: str = typer.Option("default", "--profile"),
    include_host: list[str] = typer.Option(
        [],
        "--host",
        help="Provider host to include. Repeatable. Default: subscription/OAuth allowlist.",
    ),
    include_paid: bool = typer.Option(
        False,
        "--include-paid",
        help="Include every authenticated catalog host, including paid API-key providers.",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run chat-roundtrip once for one model per selected provider host.

    This suite is intentionally explicit and is not part of ``verify all``:
    it can spend live provider quota across multiple hosts.
    """
    state = _load_state(profile)
    result = _run_one_command(
        state,
        lambda client: run_all_providers_scenario(
            state,
            client,
            include_hosts=set(include_host),
            include_paid=include_paid,
        ),
        json_out=json_out,
        label="all-providers",
    )
    emit_and_exit(result, json_out=json_out, label="all-providers")


@app.command("all")
def verify_all(
    profile: str = typer.Option("default", "--profile"),
    include: str | None = typer.Option(
        None,
        "--include",
        help="Comma-separated suites to run (default: all). Names: codex,chat-roundtrip,model-switch,telegram,cost,lcm.",
    ),
    exclude: str | None = typer.Option(
        None,
        "--exclude",
        help="Comma-separated suites to skip.",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run every configured verify suite and aggregate results.

    Exits 0 if all selected suites pass, 6 if any suite has a failed check.

    Examples:
      paw verify all
      paw verify all --json | jq '.[] | {scenario, passed}'
      paw verify all --include chat-roundtrip,model-switch
      paw verify all --exclude codex --json
    """
    state = _load_state(profile)
    selected = _select_suites(include=include, exclude=exclude)
    results = _run_many_command(state, selected, json_out=json_out, label="all")

    emit_many_and_exit(results, json_out=json_out)


def _select_suites(*, include: str | None, exclude: str | None) -> tuple[str, ...]:
    """Apply ``--include`` / ``--exclude`` filters in canonical order."""
    if include is not None:
        requested = tuple(s.strip() for s in include.split(",") if s.strip())
        unknown = [s for s in requested if s not in DEFAULT_SUITES]
        if unknown:
            raise LocalError(
                f"Unknown suite(s): {unknown}",
                hint=f"Valid suites: {', '.join(DEFAULT_SUITES)}",
            )
        chosen: tuple[str, ...] = requested
    else:
        chosen = DEFAULT_SUITES

    if exclude is not None:
        skipped = {s.strip() for s in exclude.split(",") if s.strip()}
        chosen = tuple(s for s in chosen if s not in skipped)

    if not chosen:
        raise LocalError(
            "No suites selected after applying --include/--exclude.",
            hint=f"Valid suites: {', '.join(DEFAULT_SUITES)}",
        )
    return chosen


SuiteRunner = Callable[[PawClient], Awaitable[ScenarioResult]]


def _suite_runner(state: PersonaState, name: str) -> SuiteRunner:
    """Return the async runner for a named suite. Raises on unknown names."""
    runners: dict[str, SuiteRunner] = {
        "codex": lambda client: run_codex_scenario(state, client),
        "chat-roundtrip": lambda client: run_chat_roundtrip_scenario(state, client),
        "model-switch": lambda client: run_model_switch_scenario(state, client),
        "telegram": lambda client: run_telegram_scenario(state, client),
        "google-chat": lambda client: run_google_chat_scenario(state, client),
        "cost": lambda client: run_cost_scenario(state, client),
        "lcm": lambda client: run_lcm_scenario(state, client),
    }
    runner = runners.get(name)
    if runner is None:
        raise LocalError(
            f"Unknown suite: {name}",
            hint=f"Valid suites: {', '.join(DEFAULT_SUITES)}",
        )
    return runner


async def _run_many(state: PersonaState, suites: tuple[str, ...]) -> list[ScenarioResult]:
    """Run each suite sequentially under one shared ``PawClient``."""
    results: list[ScenarioResult] = []
    async with PawClient(state, timeout=SCENARIO_HTTP_TIMEOUT_SECONDS) as client:
        for name in suites:
            runner = _suite_runner(state, name)
            results.append(await runner(client))
    return results


def _load_state(profile: str) -> PersonaState:
    """Load persona state or raise a paw ``LocalError`` if missing."""
    try:
        return PersonaState.load(profile)
    except FileNotFoundError as e:
        raise LocalError(
            f"No persona state for profile {profile!r}.",
            hint="Run `paw login` first.",
        ) from e


async def _run_one(state: PersonaState, runner: SuiteRunner) -> ScenarioResult:
    """Open one ``PawClient`` and dispatch a single scenario runner."""
    async with PawClient(state, timeout=SCENARIO_HTTP_TIMEOUT_SECONDS) as client:
        return await runner(client)


def _run_one_command(
    state: PersonaState,
    runner: SuiteRunner,
    *,
    json_out: bool,
    label: str,
) -> ScenarioResult:
    try:
        return asyncio.run(_run_one(state, runner))
    except PawError as exc:
        emit_runtime_error(label, exc, json_out=json_out)
        raise typer.Exit(exc.exit_code) from exc


def _run_many_command(
    state: PersonaState,
    suites: tuple[str, ...],
    *,
    json_out: bool,
    label: str,
) -> list[ScenarioResult]:
    try:
        return asyncio.run(_run_many(state, suites))
    except PawError as exc:
        emit_runtime_error(label, exc, json_out=json_out)
        raise typer.Exit(exc.exit_code) from exc
