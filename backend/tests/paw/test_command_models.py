"""Tests for ``paw models ls`` against a respx-mocked backend."""

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


def _seed_persona(profile: str = "default") -> PersonaState:
    state = PersonaState(
        profile=profile,
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
    )
    state.save()
    jar = load_cookies(cookies_path(profile))
    save_cookies(jar, cookies_path(profile))
    return state


@pytest.fixture
def seeded() -> PersonaState:
    return _seed_persona()


def _model_option(model_id: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": model_id,
        "host": "openai",
        "vendor": "openai",
        "model": model_id,
        "display_name": model_id.upper(),
        "short_name": model_id,
        "description": "test model",
    }
    base.update(overrides)
    return base


def test_models_ls_unwraps_envelope(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw models ls --json` iterates the envelope's ``models`` array."""
    envelope = {
        "models": [
            _model_option("gpt-4o", host="openai"),
            _model_option("claude-3-5", host="anthropic", vendor="anthropic"),
        ],
    }
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=envelope))
        result = runner.invoke(app, ["models", "ls", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert {m["id"] for m in out} == {"gpt-4o", "claude-3-5"}


def test_models_ls_filters_by_host(runner: CliRunner, seeded: PersonaState) -> None:
    envelope = {
        "models": [
            _model_option("gpt-4o", host="openai"),
            _model_option("claude-3-5", host="anthropic"),
        ],
    }
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json=envelope))
        result = runner.invoke(app, ["models", "ls", "--host", "openai", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert [m["id"] for m in out] == ["gpt-4o"]


def test_models_ls_empty_envelope(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty ``models`` array round-trips as an empty JSON list."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(return_value=httpx.Response(200, json={"models": []}))
        result = runner.invoke(app, ["models", "ls", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []


def test_models_ls_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """Backend 401 surfaces as AuthError exit 3."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/models").mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )
        result = runner.invoke(app, ["models", "ls"])

    assert result.exit_code == 3


def test_models_ls_rejects_json_and_plain_together(runner: CliRunner, seeded: PersonaState) -> None:
    result = runner.invoke(app, ["models", "ls", "--json", "--plain"])
    assert result.exit_code == 1
