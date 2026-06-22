"""Lazy imports for ``paw verify`` scenarios.

Keeping these wrappers out of ``commands.verify`` prevents the CLI command
module from loading provider SDKs at startup while preserving the public
monkeypatch seam used by tests.
"""

from __future__ import annotations

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify.scenarios import ScenarioResult

# <skill-gen>
# ---
# name: paw
# description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user -- auth, workspaces, chat with SSE streaming, conversation CRUD, provider verification. Prefer this over importing `app.*` modules in ad-hoc Python scripts; `paw` exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to `paw`.
# ---
#
# ## Verification workflows
#
# ```bash
# just paw verify codex --json
# just paw verify chat-roundtrip --model litellm:openai/gpt-4o-mini --json
# just paw verify model-switch --from litellm:openai/gpt-4o-mini --to litellm:anthropic/Codex-3-5-sonnet --json
# just paw verify telegram --json
# just paw verify google-chat --json
# just paw verify cost --json
# just paw verify lcm --json
# just paw verify all-providers --json
# just paw verify all --json
# ```
#
# Use `jq '.checks[] | select(.passed == false)'` on JSON output to focus on
# failing assertions. `paw verify all` runs the shippable suites in sequence and
# exits 6 if any suite fails.
#
# `paw verify lcm` currently emits stable marker checks for blocked active-recall
# endpoints (`memory_seeding_endpoint_unavailable` and
# `dreaming_trigger_endpoint_unavailable`) until `pawrrtal-x9u4` lands.
# </skill-gen>


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
    from app.cli.paw.verify.model_switch import (  # noqa: PLC0415
        run_model_switch_scenario as run,
    )

    return await run(
        state,
        client,
        from_override=from_override,
        to_override=to_override,
    )


async def run_telegram_scenario(state: PersonaState, client: PawClient) -> ScenarioResult:
    """Import and run the Telegram scenario lazily."""
    from app.cli.paw.verify.telegram import (  # noqa: PLC0415
        run_telegram_scenario as run,
    )

    return await run(state, client)


async def run_google_chat_scenario(state: PersonaState, client: PawClient) -> ScenarioResult:
    """Import and run the Google Chat scenario lazily."""
    from app.cli.paw.verify.google_chat import (  # noqa: PLC0415
        run_google_chat_scenario as run,
    )

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
    from app.cli.paw.verify.all_providers import (  # noqa: PLC0415
        run_all_providers_scenario as run,
    )

    return await run(
        state,
        client,
        include_hosts=include_hosts,
        include_paid=include_paid,
    )
