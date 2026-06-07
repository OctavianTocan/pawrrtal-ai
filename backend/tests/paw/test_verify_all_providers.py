"""Tests for ``paw verify all-providers``."""

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
CONV_IDS = [
    "11111111-2222-3333-4444-555555555555",
    "22222222-3333-4444-5555-666666666666",
]


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in persona rooted at the mocked backend."""
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
def stable_uuids(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ids = iter(CONV_IDS)
    monkeypatch.setattr("app.cli.paw.ids.new_conversation_id", lambda: next(ids))
    return CONV_IDS


def _catalog() -> dict[str, Any]:
    return {
        "models": [
            {
                "model_id": "agy-api:google/gemini-3.5-flash-low",
                "id": "agy-api:google/gemini-3.5-flash-low",
                "host": "agy-api",
            },
            {
                "model_id": "openai-codex:openai/gpt-5.5",
                "id": "openai-codex:openai/gpt-5.5",
                "host": "openai-codex",
            },
            {
                "model_id": "litellm:openai/gpt-4o-mini",
                "id": "litellm:openai/gpt-4o-mini",
                "host": "litellm",
            },
        ]
    }


def _sse_body(content: str) -> bytes:
    return (
        f'data: {{"type": "delta", "content": "{content}"}}\n\ndata: {{"type": "done"}}\n\n'
    ).encode()


def _wire_roundtrip(router: respx.MockRouter, conv_id: str, content: str) -> None:
    router.post(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json={"id": conv_id, "title": "provider"})
    )
    router.get(f"/api/v1/conversations/{conv_id}/messages").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"role": "user", "content": "Say hello briefly."},
                {
                    "role": "assistant",
                    "content": content,
                    "thinking": None,
                    "tool_calls": [],
                    "timeline": [],
                    "thinking_duration_seconds": None,
                    "assistant_status": "complete",
                },
            ],
        )
    )
    router.delete(f"/api/v1/conversations/{conv_id}").mock(return_value=httpx.Response(204))


def test_verify_all_providers_runs_one_roundtrip_per_allowed_host(
    runner: CliRunner,
    seeded: PersonaState,
    stable_uuids: list[str],
) -> None:
    """The suite picks one authenticated catalog model per allowed provider host."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as router:
        router.get("/api/v1/models").mock(return_value=httpx.Response(200, json=_catalog()))
        router.post("/api/v1/chat/").mock(
            side_effect=[
                httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=_sse_body("agy ok"),
                ),
                httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=_sse_body("codex ok"),
                ),
            ]
        )
        _wire_roundtrip(router, stable_uuids[0], "agy ok")
        _wire_roundtrip(router, stable_uuids[1], "codex ok")
        result = runner.invoke(app, ["verify", "all-providers", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["scenario"] == "all-providers"
    assert payload["passed"] is True
    selected = payload["artifacts"]["selected_models"]
    assert [row["host"] for row in selected] == ["agy-api", "openai-codex"]
    assert {check["name"] for check in payload["checks"]} >= {
        "provider_agy_api_passed",
        "provider_openai_codex_passed",
    }


def test_verify_all_providers_requires_at_least_one_selected_model(
    runner: CliRunner,
    seeded: PersonaState,
) -> None:
    """A catalog with no allowed provider hosts fails with a named check."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as router:
        router.get("/api/v1/models").mock(
            return_value=httpx.Response(
                200,
                json={"models": [{"model_id": "litellm:openai/gpt-4o-mini", "host": "litellm"}]},
            )
        )
        result = runner.invoke(app, ["verify", "all-providers", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    assert "provider_models_selected" in {
        check["name"] for check in payload["checks"] if not check["passed"]
    }
