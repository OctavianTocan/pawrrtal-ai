"""Tests for ``paw verify lcm`` against a respx-mocked backend.

Covers the happy path + the failure modes for every structural check
the scenario emits. The full active-recall E2E (seed memory -> dream ->
recall on a later turn) is blocked on backend work (``pawrrtal-x9u4``);
those two marker checks are asserted as stable passing rows.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
FIXED_UUID = "11111111-2222-3333-4444-555555555555"
DEFAULT_MODEL = "openai-codex:openai/gpt-5.5"

# One healthy chat stream — two delta events + done sentinel. Mirrors
# the SSE_OK fixture in the sibling verify tests.
SSE_OK = (
    b'data: {"type": "delta", "content": "Hi"}\n\n'
    b'data: {"type": "delta", "content": " there"}\n\n'
    b'data: {"type": "done"}\n\n'
)


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in ``PersonaState`` + non-empty cookie jar."""
    state = PersonaState(
        profile=profile,
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
        default_workspace_id="ws-1",
    )
    state.save()
    jar = load_cookies(cookies_path(profile))
    save_cookies(jar, cookies_path(profile))
    return state


@pytest.fixture
def seeded() -> PersonaState:
    return _seed_persona()


@pytest.fixture
def stable_uuid(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("app.cli.paw.ids.new_conversation_id", lambda: FIXED_UUID)
    return FIXED_UUID


def _models_payload() -> dict[str, Any]:
    return {
        "models": [
            {"model_id": DEFAULT_MODEL, "id": DEFAULT_MODEL, "is_default": True},
        ]
    }


def _lcm_payload(
    *,
    conversation_id: str = FIXED_UUID,
    lcm_enabled: bool = True,
    fresh_tail_count: int = 16,
    items: list[dict[str, Any]] | None = None,
    estimated_tokens: int = 42,
) -> dict[str, Any]:
    """Build an LCMContextDebugResponse-shaped envelope."""
    resolved_items = (
        items
        if items is not None
        else [
            {
                "ordinal": 0,
                "item_kind": "message",
                "item_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "role": "user",
                "preview": "My favourite colour is teal.",
                "token_count": 7,
            },
            {
                "ordinal": 1,
                "item_kind": "message",
                "item_id": "11111111-2222-3333-4444-555555555550",
                "role": "assistant",
                "preview": "Noted.",
                "token_count": 2,
            },
        ]
    )
    return {
        "conversation_id": conversation_id,
        "lcm_enabled": lcm_enabled,
        "fresh_tail_count": fresh_tail_count,
        "item_count": len(resolved_items),
        "message_count": sum(1 for i in resolved_items if i.get("item_kind") == "message"),
        "summary_count": sum(1 for i in resolved_items if i.get("item_kind") == "summary"),
        "estimated_tokens": estimated_tokens,
        "items": resolved_items,
        "settings": {
            "lcm_enabled": lcm_enabled,
            "fresh_tail_count": fresh_tail_count,
            "leaf_chunk_tokens": 256,
            "incremental_max_depth": 3,
        },
    }


def _mock_happy_path(
    r: respx.MockRouter,
    conv_id: str,
    *,
    sse: bytes = SSE_OK,
    lcm_response: dict[str, Any] | None = None,
    lcm_status: int = 200,
) -> None:
    """Wire every endpoint the scenario touches to a healthy response."""
    payload = lcm_response if lcm_response is not None else _lcm_payload(conversation_id=conv_id)

    r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
    r.post(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json={"id": conv_id, "title": "paw verify lcm"})
    )
    r.post("/api/v1/chat/").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)
    )
    r.get(f"/api/v1/lcm/conversations/{conv_id}/context").mock(
        return_value=httpx.Response(lcm_status, json=payload)
    )
    r.delete(f"/api/v1/conversations/{conv_id}").mock(return_value=httpx.Response(204))


def _failed_check_names(payload: dict[str, Any]) -> list[str]:
    """Names of all failed checks in a JSON-dumped scenario result."""
    return [c["name"] for c in payload["checks"] if not c["passed"]]


def _all_check_names(payload: dict[str, Any]) -> set[str]:
    """Names of every check (passed or failed)."""
    return {c["name"] for c in payload["checks"]}


def test_happy_path_passes_every_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """All canonical checks pass when the backend behaves."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "lcm", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert _failed_check_names(payload) == []
    names = _all_check_names(payload)
    # Pin every canonical name so a future rename surfaces immediately.
    assert {
        "model_resolved",
        "conversation_created",
        "turn_one_streamed",
        "turn_two_streamed",
        "lcm_context_endpoint_reachable",
        "lcm_context_lcm_enabled",
        "lcm_context_fresh_tail_present",
        "lcm_context_items_shape",
        "lcm_context_estimated_tokens_nonneg",
        "memory_seeding_endpoint_unavailable",
        "dreaming_trigger_endpoint_unavailable",
        "conversation_cleanup",
    } <= names


def test_lcm_disabled_emits_marker_and_skips_structural_checks(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """When ``lcm_enabled`` is false the structural checks are skipped.

    The scenario still passes — a backend with LCM intentionally off is
    a valid configuration. The greppable ``lcm_disabled_in_this_env``
    marker tells consumers what happened.
    """
    disabled_payload = _lcm_payload(conversation_id=stable_uuid, lcm_enabled=False, items=[])
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, lcm_response=disabled_payload)
        result = runner.invoke(app, ["verify", "lcm", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    names = _all_check_names(payload)
    assert "lcm_disabled_in_this_env" in names
    # Structural checks are skipped when LCM is disabled.
    assert "lcm_context_fresh_tail_present" not in names
    assert "lcm_context_items_shape" not in names
    assert "lcm_context_estimated_tokens_nonneg" not in names


def test_models_401_exits_3(runner: CliRunner, seeded: PersonaState, stable_uuid: str) -> None:
    """A 401 on the initial GET /api/v1/models surfaces as AuthError (exit 3).

    The model-catalog GET is the first authed call in the scenario, so
    it's where the AuthError -> exit 3 contract is exercised. The chat
    SSE path raises on ``raise_for_status`` and is therefore covered by
    integration tests rather than the unit harness.
    """
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["verify", "lcm", "--json"])
    assert result.exit_code == 3, result.stdout


def test_lcm_endpoint_500_exits_5(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A 500 on the LCM context endpoint surfaces as ApiError (exit 5).

    ``PawClient.request`` raises ``ApiError`` (exit 5) on any unexpected
    status; the LCM scenario doesn't catch — the failure is visible to
    operators as an exit-5 with the upstream body preview, which is
    exactly what we want when the backend is broken.
    """
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, lcm_status=500, lcm_response={"detail": "boom"})
        result = runner.invoke(app, ["verify", "lcm", "--json"])
    assert result.exit_code == 5, result.stdout


def test_empty_items_list_still_passes_items_shape(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """An empty ``items`` list is a valid shape — no compaction yet."""
    empty = _lcm_payload(conversation_id=stable_uuid, items=[], estimated_tokens=0)
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, lcm_response=empty)
        result = runner.invoke(app, ["verify", "lcm", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    # Items shape check should still pass on empty list.
    names_by_pass = {c["name"]: c["passed"] for c in payload["checks"]}
    assert names_by_pass.get("lcm_context_items_shape") is True


def test_seed_and_dream_markers_always_present_on_happy_path(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """Marker checks ship on every happy-path run as a greppable gap signal.

    Consumers (CI dashboards, agents) grep for the names to spot the
    missing endpoints; the day a memory-seed + dreaming-trigger route
    lands, these should be replaced with real enforcement assertions.
    """
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "lcm", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    seed = next(
        (c for c in payload["checks"] if c["name"] == "memory_seeding_endpoint_unavailable"),
        None,
    )
    dream = next(
        (c for c in payload["checks"] if c["name"] == "dreaming_trigger_endpoint_unavailable"),
        None,
    )
    assert seed is not None and seed["passed"] is True
    assert dream is not None and dream["passed"] is True
    assert "pawrrtal-x9u4" in seed["detail"]
    assert "pawrrtal-x9u4" in dream["detail"]


def test_empty_final_text_short_circuits_with_markers(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A stream with no text events fails turn_one and still emits markers."""
    empty_sse = b'data: {"type": "done"}\n\n'
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid, sse=empty_sse)
        result = runner.invoke(app, ["verify", "lcm", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    failed = _failed_check_names(payload)
    assert "turn_one_streamed" in failed
    # Marker still emitted even on short-circuit so downstream tooling
    # can grep for the gap regardless of upstream chat health.
    names = _all_check_names(payload)
    assert "memory_seeding_endpoint_unavailable" in names
    assert "dreaming_trigger_endpoint_unavailable" in names


def test_json_shape_matches_scenario_result(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """``--json`` emits the canonical ScenarioResult shape."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "lcm", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["scenario"] == "lcm"
    assert isinstance(payload["passed"], bool)
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["artifacts"], dict)
    # Every artifact key we promise to emit on the happy path.
    assert "turn_one_events" in payload["artifacts"]
    assert "turn_two_events" in payload["artifacts"]
    assert "lcm_context_response" in payload["artifacts"]
