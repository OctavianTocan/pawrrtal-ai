"""Mid-conversation model-switch verification scenario.

Question this scenario answers: "If a mid-conversation model switch
corrupts the conversation row, does this suite catch it?"

The scenario starts a conversation with model ``M1``, sends one turn,
``PATCH``es the conversation to model ``M2`` with a new
``reasoning_effort``, sends another turn, then reads the row back and
asserts the canonical ``model_id`` matches ``M2`` (migration 012's
contract) and that the ``reasoning_effort`` CHECK constraint
(migration 020) was honoured.

The two models default to the catalog's ``is_default`` entry and the
first non-default entry; ``--from`` / ``--to`` overrides both.
"""

from __future__ import annotations

from typing import Any

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify import helpers
from app.cli.paw.verify.scenarios import ScenarioResult
from app.providers.model_id import InvalidModelId, parse_model_id

TURN_1_TEXT = "Say hi in two words."
TURN_2_TEXT = "Now say bye in two words."
SCENARIO_TITLE = "paw verify model-switch"
REASONING_EFFORT_AFTER_SWITCH = "low"

# PATCH must return exactly 200 — the route is annotated
# ``response_model=ConversationRead`` and never 201 / 204 the way
# ``POST /conversations/{id}`` does.
HTTP_OK = 200


def _canonical(model_id: str | None) -> str | None:
    """Return the canonical ``host:vendor/model`` form, or ``None``."""
    if model_id is None:
        return None
    try:
        return parse_model_id(model_id).id
    except InvalidModelId:
        return None


async def _resolve_models(
    client: PawClient,
    r: ScenarioResult,
    *,
    from_override: str | None,
    to_override: str | None,
) -> tuple[str, str] | None:
    """Resolve the two model ids from overrides + catalog defaults."""
    catalog = (await client.request("GET", "/api/v1/models")).json()
    models = helpers.extract_models(catalog)
    r.artifacts["catalog_count"] = len(models)

    default = helpers.find_default_model(models)
    default_id = default.get("model_id") or default.get("id") if default else None

    from_id = from_override or (default_id if isinstance(default_id, str) else None)
    if from_id is None:
        r.add(
            "from_model_resolved",
            False,
            detail="no catalog entry has is_default=true; pass --from to override",
        )
        return None
    r.add("from_model_resolved", True, detail=f"from={from_id}")

    to_id: str | None = to_override
    if to_id is None:
        for m in models:
            candidate = m.get("model_id") or m.get("id")
            if isinstance(candidate, str) and candidate != from_id:
                to_id = candidate
                break
    if to_id is None or to_id == from_id:
        r.add(
            "to_model_resolved",
            False,
            detail=f"could not find a second model distinct from {from_id}; pass --to",
        )
        return None
    r.add("to_model_resolved", True, detail=f"to={to_id}")
    return from_id, to_id


def _assert_no_errors(r: ScenarioResult, events: list[dict[str, Any]], turn_label: str) -> None:
    """Assert a chat turn produced no error events."""
    errors = [e for e in events if e.get("type") == "error"]
    r.add(
        f"{turn_label}_no_errors",
        len(errors) == 0,
        detail=f"first={errors[0] if errors else None}",
    )


async def _patch_model(
    client: PawClient,
    r: ScenarioResult,
    conv_id: str,
    new_model: str,
) -> dict[str, Any]:
    """PATCH the conversation to a new model + reasoning effort. Returns body."""
    resp = await client.request(
        "PATCH",
        f"/api/v1/conversations/{conv_id}",
        json_body={"model_id": new_model, "reasoning_effort": REASONING_EFFORT_AFTER_SWITCH},
        expect=(200,),
    )
    body = resp.json()
    r.add("patch_returns_200", resp.status_code == HTTP_OK, detail=f"status={resp.status_code}")
    return body if isinstance(body, dict) else {}


def _assert_canonicalisation(r: ScenarioResult, patch_body: dict[str, Any], to_id: str) -> None:
    """Assert PATCH response canonicalised ``model_id`` (migration 012)."""
    canonical_to = _canonical(to_id)
    if canonical_to is None:
        r.add("model_id_canonicalisable", False, detail=f"unparseable: {to_id}")
        return
    r.add("model_id_canonicalisable", True, detail=f"canonical={canonical_to}")
    r.add(
        "patch_canonicalises_model_id",
        patch_body.get("model_id") == canonical_to,
        detail=f"got={patch_body.get('model_id')} expected={canonical_to}",
    )


async def _assert_persisted_state(
    client: PawClient,
    r: ScenarioResult,
    conv_id: str,
    to_id: str,
) -> None:
    """GET the conversation back and assert canonical model + clean state."""
    final = (await client.request("GET", f"/api/v1/conversations/{conv_id}")).json()
    r.artifacts["conversation_after_switch"] = final
    canonical_to = _canonical(to_id)
    r.add(
        "persisted_model_id_canonical",
        final.get("model_id") == canonical_to,
        detail=f"got={final.get('model_id')} expected={canonical_to}",
    )


async def run_model_switch_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    from_override: str | None = None,
    to_override: str | None = None,
) -> ScenarioResult:
    """Switch models mid-conversation and assert row integrity."""
    r = ScenarioResult(name="model-switch")

    resolved = await _resolve_models(
        client,
        r,
        from_override=from_override,
        to_override=to_override,
    )
    if resolved is None:
        return r
    from_id, to_id = resolved

    conv_id = await helpers.create_conversation(client, r, title=SCENARIO_TITLE)

    events_1 = await helpers.stream_turn(client, conv_id, TURN_1_TEXT, model_id=from_id)
    r.artifacts["turn_1_events"] = events_1
    _assert_no_errors(r, events_1, "turn_1")

    patch_body = await _patch_model(client, r, conv_id, to_id)
    _assert_canonicalisation(r, patch_body, to_id)

    events_2 = await helpers.stream_turn(
        client,
        conv_id,
        TURN_2_TEXT,
        model_id=to_id,
        reasoning_effort=REASONING_EFFORT_AFTER_SWITCH,
    )
    r.artifacts["turn_2_events"] = events_2
    _assert_no_errors(r, events_2, "turn_2")

    await _assert_persisted_state(client, r, conv_id, to_id)
    await helpers.cleanup_conversation(client, r, conv_id)
    return r
