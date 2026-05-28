"""End-to-end LCM active-recall observability verification scenario.

Drives the real chat surface (``POST /api/v1/conversations/{uuid}`` ->
``POST /api/v1/chat/`` x2 -> ``GET /api/v1/lcm/conversations/{id}/context``
-> ``DELETE /api/v1/conversations/{uuid}``) and asserts the LCM debug
context endpoint exposes the assembled-context observability view for
the resulting conversation.

Scope note — the *full* active-recall E2E (seeded memories appearing in
turn N+1's pre-turn assembly after a dreaming pass) requires backend
HTTP surfaces that do not exist today: a memory-seeding endpoint and
a dreaming trigger. Both are tracked in ``pawrrtal-x9u4``. Until they
land, this scenario emits two stable greppable marker checks
(``memory_seeding_endpoint_unavailable`` and
``dreaming_trigger_endpoint_unavailable``) so consumers can key off
the gap and flip them to real assertions the moment the endpoints
ship.

What this scenario *does* prove today: two chat turns flow through
the real chat router, the LCM debug endpoint returns 200 for the
resulting conversation, and the response shape matches the
``LCMContextDebugResponse`` schema (``items``, ``fresh_tail_count``,
``estimated_tokens``, ``lcm_enabled``). When ``lcm_enabled`` is false
in the environment, structural item-shape checks are skipped and a
``lcm_disabled_in_this_env`` marker is emitted instead so the scenario
stays green on a backend where LCM is intentionally off.
"""

from __future__ import annotations

from typing import Any

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify import helpers
from app.cli.paw.verify.scenarios import ScenarioResult

# Turn texts — turn 1 introduces a memorable fact, turn 2 asks for
# it back. We deliberately do not assert that the model *recalls* the
# fact (LLM-quality assertion, not a structural one); we only assert
# both turns produce non-empty ``final_text``.
TURN_ONE_TEXT = "My favourite colour is teal. Please remember that."
TURN_TWO_TEXT = "What's my favourite colour?"
SCENARIO_TITLE = "paw verify lcm"

# Successful response status for the LCM debug endpoint. The route is
# read-only and returns 200 even when the underlying conversation has
# no compacted items yet (the response just lists zero items).
LCM_CONTEXT_OK_STATUS = 200


def _assemble_final_text(events: list[dict[str, Any]]) -> str:
    """Concatenate text-bearing events the way the frontend renderer does."""
    parts: list[str] = []
    for e in events:
        if e.get("type") not in ("delta", "message"):
            continue
        content = e.get("content")
        if isinstance(content, str):
            parts.append(content)
    return "".join(parts)


def _assert_turn(
    r: ScenarioResult,
    events: list[dict[str, Any]],
    *,
    check_name: str,
) -> bool:
    """Assert one chat turn streamed text with no errors. Return True on success."""
    errors = [e for e in events if e.get("type") == "error"]
    final_text = _assemble_final_text(events)
    passed = len(errors) == 0 and bool(final_text.strip())
    r.add(
        check_name,
        passed,
        detail=(
            f"errors={len(errors)} final_text={final_text[:60]!r}"
            if not passed
            else f"final_text={final_text[:60]!r}"
        ),
    )
    return passed


async def _drive_two_turns(
    client: PawClient,
    r: ScenarioResult,
    *,
    model_id: str,
) -> str | None:
    """Create a conversation and stream two turns. Returns conversation id."""
    conv_id = await helpers.create_conversation(client, r, title=SCENARIO_TITLE)

    events_one = await helpers.stream_turn(client, conv_id, TURN_ONE_TEXT, model_id=model_id)
    r.artifacts["turn_one_events"] = events_one
    if not _assert_turn(r, events_one, check_name="turn_one_streamed"):
        return conv_id

    events_two = await helpers.stream_turn(client, conv_id, TURN_TWO_TEXT, model_id=model_id)
    r.artifacts["turn_two_events"] = events_two
    _assert_turn(r, events_two, check_name="turn_two_streamed")
    return conv_id


def _assert_lcm_structural(r: ScenarioResult, payload: dict[str, Any]) -> None:
    """Assert structural fields of the LCM debug response when LCM is enabled."""
    fresh_tail = payload.get("fresh_tail_count")
    r.add(
        "lcm_context_fresh_tail_present",
        isinstance(fresh_tail, int) and fresh_tail >= 0,
        detail=f"fresh_tail_count={fresh_tail!r}",
    )

    items = payload.get("items")
    items_ok = isinstance(items, list) and all(
        isinstance(item, dict) and "ordinal" in item and "item_kind" in item for item in items
    )
    r.add(
        "lcm_context_items_shape",
        items_ok,
        detail=f"items_count={len(items) if isinstance(items, list) else 'N/A'}",
    )

    estimated = payload.get("estimated_tokens")
    r.add(
        "lcm_context_estimated_tokens_nonneg",
        isinstance(estimated, int) and estimated >= 0,
        detail=f"estimated_tokens={estimated!r}",
    )


async def _fetch_lcm_context(
    client: PawClient,
    r: ScenarioResult,
    conv_id: str,
) -> dict[str, Any] | None:
    """GET the LCM debug context and assert reachability + ``lcm_enabled`` field.

    Returns the response payload when the endpoint returned 200 with a
    valid envelope; ``None`` otherwise (the caller short-circuits the
    remaining structural checks).
    """
    resp = await client.request(
        "GET",
        f"/api/v1/lcm/conversations/{conv_id}/context",
        expect=(LCM_CONTEXT_OK_STATUS,),
    )
    r.add(
        "lcm_context_endpoint_reachable",
        resp.status_code == LCM_CONTEXT_OK_STATUS,
        detail=f"status={resp.status_code}",
    )
    payload = resp.json() if isinstance(resp.json(), dict) else None
    r.artifacts["lcm_context_response"] = payload

    if payload is None:
        r.add(
            "lcm_context_lcm_enabled",
            False,
            detail="response body was not a JSON object",
        )
        return None

    lcm_enabled = payload.get("lcm_enabled")
    r.add(
        "lcm_context_lcm_enabled",
        isinstance(lcm_enabled, bool),
        detail=f"lcm_enabled={lcm_enabled!r}",
    )

    if lcm_enabled is False:
        r.add(
            "lcm_disabled_in_this_env",
            True,
            detail=(
                "settings.lcm_enabled is false; structural item-shape "
                "checks skipped. Flip `LCM_ENABLED=true` to exercise the "
                "full assembly path."
            ),
        )
        return None

    # mypy: payload is already narrowed to ``dict[str, Any]`` above; the
    # explicit dict() copy lets the type checker see it concretely.
    return dict(payload)


def _record_seed_and_dream_gaps(r: ScenarioResult) -> None:
    """Document the missing memory-seed + dreaming-trigger endpoints.

    Both checks pass intentionally — there is nothing for paw to break
    because the endpoints do not exist. The greppable names let agents
    and dashboards key off the gap and flip them to real assertions the
    moment ``POST /api/v1/lcm/memories`` (or analogous) and a dreaming
    trigger route land. Both gaps are tracked in ``pawrrtal-x9u4``.
    """
    r.add(
        "memory_seeding_endpoint_unavailable",
        True,
        detail=(
            "No HTTP endpoint exists to seed LCM memories from outside "
            "the agent loop; full active-recall E2E (seed -> dream -> "
            "recall) is blocked on pawrrtal-x9u4."
        ),
    )
    r.add(
        "dreaming_trigger_endpoint_unavailable",
        True,
        detail=(
            "No HTTP endpoint exists to trigger a dreaming pass on demand; "
            "the compaction worker runs on its own schedule. Blocked on "
            "pawrrtal-x9u4."
        ),
    )


async def run_lcm_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    model: str | None = None,
) -> ScenarioResult:
    """Drive two chat turns and assert the LCM observability surface.

    Sequence: resolve model -> create conversation -> turn 1 -> turn 2 ->
    GET lcm context -> structural shape assertions -> seed/dream gap
    markers -> cleanup. The full active-recall path (seeded memories
    surfacing after a dreaming pass) is blocked on backend work
    (``pawrrtal-x9u4``); two marker checks are emitted to make the gap
    greppable.
    """
    r = ScenarioResult(name="lcm")
    del state  # PersonaState carried by ``client``; kept for runner parity.

    model_id = await helpers.resolve_default_model(client, r, model)
    if model_id is None:
        return r

    conv_id = await _drive_two_turns(client, r, model_id=model_id)
    if conv_id is None:
        _record_seed_and_dream_gaps(r)
        return r

    payload = await _fetch_lcm_context(client, r, conv_id)
    if payload is not None:
        _assert_lcm_structural(r, payload)

    _record_seed_and_dream_gaps(r)
    await helpers.cleanup_conversation(client, r, conv_id)
    return r
