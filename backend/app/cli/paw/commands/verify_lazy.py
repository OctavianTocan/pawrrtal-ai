"""Lazy imports for ``paw verify`` scenarios.

Keeping these wrappers out of ``commands.verify`` prevents the CLI command
module from loading provider SDKs at startup while preserving the public
monkeypatch seam used by tests.
"""

from __future__ import annotations

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify.scenarios import ScenarioResult


async def run_codex_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    keep_conversation: bool = False,
) -> ScenarioResult:
    """Import and run the Codex scenario lazily."""
    from app.cli.paw.verify.codex import run_codex_scenario as run  # noqa: PLC0415

    return await run(state, client, keep_conversation=keep_conversation)


async def run_chat_roundtrip_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    model_override: str | None = None,
) -> ScenarioResult:
    """Import and run the chat roundtrip scenario lazily."""
    from app.cli.paw.verify.chat_roundtrip import (  # noqa: PLC0415
        run_chat_roundtrip_scenario as run,
    )

    return await run(state, client, model_override=model_override)


async def run_model_switch_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    from_override: str | None = None,
    to_override: str | None = None,
) -> ScenarioResult:
    """Import and run the model-switch scenario lazily."""
    from app.cli.paw.verify.model_switch import run_model_switch_scenario as run  # noqa: PLC0415

    return await run(
        state,
        client,
        from_override=from_override,
        to_override=to_override,
    )


async def run_telegram_scenario(state: PersonaState, client: PawClient) -> ScenarioResult:
    """Import and run the Telegram scenario lazily."""
    from app.cli.paw.verify.telegram import run_telegram_scenario as run  # noqa: PLC0415

    return await run(state, client)


async def run_google_chat_scenario(state: PersonaState, client: PawClient) -> ScenarioResult:
    """Import and run the Google Chat scenario lazily."""
    from app.cli.paw.verify.google_chat import run_google_chat_scenario as run  # noqa: PLC0415

    return await run(state, client)


async def run_cost_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    model_override: str | None = None,
) -> ScenarioResult:
    """Import and run the cost scenario lazily."""
    from app.cli.paw.verify.cost import run_cost_scenario as run  # noqa: PLC0415

    return await run(state, client, model_override=model_override)


async def run_lcm_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    model: str | None = None,
) -> ScenarioResult:
    """Import and run the LCM scenario lazily."""
    from app.cli.paw.verify.lcm import run_lcm_scenario as run  # noqa: PLC0415

    return await run(state, client, model=model)


async def run_all_providers_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    include_hosts: set[str],
    include_paid: bool,
) -> ScenarioResult:
    """Import and run the all-providers scenario lazily."""
    from app.cli.paw.verify.all_providers import run_all_providers_scenario as run  # noqa: PLC0415

    return await run(
        state,
        client,
        include_hosts=include_hosts,
        include_paid=include_paid,
    )
