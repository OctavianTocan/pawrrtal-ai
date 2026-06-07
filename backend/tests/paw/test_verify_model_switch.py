"""Tests for ``paw verify model-switch`` against a respx-mocked backend.

Covers the happy path + four distinct failure modes — wrong PATCH echo,
wrong persisted model_id after switch, PATCH 422 (CHECK constraint
simulation), and the no-second-model resolution path.
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
FIXED_UUID = "22222222-3333-4444-5555-666666666666"
MODEL_FROM = "openai-codex:openai/gpt-5.5"
MODEL_TO = "agent-sdk:anthropic/claude-opus-4-7"

SSE_OK = b'data: {"type": "delta", "content": "Hi"}\n\ndata: {"type": "done"}\n\n'


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in ``PersonaState`` + a non-empty cookie jar."""
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
            {"model_id": MODEL_FROM},
            {"model_id": MODEL_TO},
        ]
    }


def _conv_payload(
    conv_id: str,
    *,
    model_id: str | None = MODEL_TO,
) -> dict[str, Any]:
    return {
        "id": conv_id,
        "user_id": "u1",
        "title": "paw verify model-switch",
        "created_at": "2026-05-27T00:00:00Z",
        "updated_at": "2026-05-27T00:00:00Z",
        "is_archived": False,
        "is_flagged": False,
        "is_unread": False,
        "status": None,
        "model_id": model_id,
        "labels": [],
        "project_id": None,
        "provider_session_id": None,
    }


def _mock_happy_path(r: respx.MockRouter, conv_id: str) -> None:
    """Wire every endpoint the scenario touches with healthy values."""
    r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_models_payload()))
    r.post(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json={"id": conv_id, "title": "x"})
    )
    r.post("/api/v1/chat/").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=SSE_OK
        )
    )
    r.patch(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json=_conv_payload(conv_id, model_id=MODEL_TO))
    )
    r.get(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json=_conv_payload(conv_id, model_id=MODEL_TO))
    )
    r.delete(f"/api/v1/conversations/{conv_id}").mock(return_value=httpx.Response(204))


def _check_names(payload: dict[str, Any]) -> list[str]:
    return [c["name"] for c in payload["checks"] if not c["passed"]]


def test_happy_path_passes_every_check(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """All canonical checks pass when the backend behaves."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        result = runner.invoke(app, ["verify", "model-switch", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True, payload
    assert _check_names(payload) == []
    names = {c["name"] for c in payload["checks"]}
    assert "patch_canonicalises_model_id" in names
    assert "persisted_model_id_canonical" in names
    assert "turn_2_no_errors" in names


def test_patch_echoes_old_model_fails_canonicalisation(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """PATCH returning the old model_id trips ``patch_canonicalises_model_id``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        r.patch(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conv_payload(stable_uuid, model_id=MODEL_FROM))
        )
        result = runner.invoke(app, ["verify", "model-switch", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "patch_canonicalises_model_id" in _check_names(payload)


def test_get_shows_old_model_fails_persistence(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """GET returning the pre-switch model trips ``persisted_model_id_canonical``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conv_payload(stable_uuid, model_id=MODEL_FROM))
        )
        result = runner.invoke(app, ["verify", "model-switch", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "persisted_model_id_canonical" in _check_names(payload)


def test_patch_422_simulates_check_constraint_failure(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """PATCH returning 422 (e.g. ``reasoning_effort`` CHECK violation) raises ApiError."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        _mock_happy_path(r, stable_uuid)
        r.patch(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(422, json={"detail": "bad reasoning_effort"})
        )
        result = runner.invoke(app, ["verify", "model-switch", "--json"])

    # API error short-circuits with exit code 5 (paw ApiError), so the
    # scenario never gets to claim success — the CHECK constraint
    # regression surfaces loudly instead of silently passing.
    assert result.exit_code == 5, result.stdout


def test_no_second_model_in_catalog_fails_resolution(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """A catalog with only one entry trips ``to_model_resolved``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(
            return_value=httpx.Response(200, json={"models": [{"model_id": MODEL_FROM}]})
        )
        result = runner.invoke(app, ["verify", "model-switch", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "to_model_resolved" in _check_names(payload)


def test_from_to_overrides_skip_catalog_defaults(
    runner: CliRunner, seeded: PersonaState, stable_uuid: str
) -> None:
    """``--from`` / ``--to`` flags resolve models even with no catalog defaults."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json={"models": []}))
        r.post(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json={"id": stable_uuid, "title": "x"})
        )
        r.post("/api/v1/chat/").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=SSE_OK
            )
        )
        r.patch(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conv_payload(stable_uuid, model_id=MODEL_TO))
        )
        r.get(f"/api/v1/conversations/{stable_uuid}").mock(
            return_value=httpx.Response(200, json=_conv_payload(stable_uuid, model_id=MODEL_TO))
        )
        r.delete(f"/api/v1/conversations/{stable_uuid}").mock(return_value=httpx.Response(204))
        result = runner.invoke(
            app,
            [
                "verify",
                "model-switch",
                "--from",
                MODEL_FROM,
                "--to",
                MODEL_TO,
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
