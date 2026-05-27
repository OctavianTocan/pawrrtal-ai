"""Tests for ``paw api`` — request passthrough + OpenAPI discovery."""

from __future__ import annotations

import json

import httpx
import respx

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
API_ERROR_EXIT_CODE = 5


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in PersonaState pointed at the mock backend."""
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


def test_api_request_get_json_envelope(runner):
    """GET /api/v1/users/me with --json returns the {status, headers, body} envelope."""
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=True) as r:
        r.get("/api/v1/users/me").mock(
            return_value=httpx.Response(200, json={"id": "u1", "email": "admin@example.com"})
        )
        result = runner.invoke(app, ["api", "request", "GET", "/api/v1/users/me", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == 200
    assert payload["body"] == {"id": "u1", "email": "admin@example.com"}


def test_api_request_post_with_stdin_body(runner):
    """--stdin feeds JSON body; the recorded request sees the parsed payload."""
    _seed_persona()
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=True) as r:
        r.post("/api/v1/conversations").mock(side_effect=_capture)
        result = runner.invoke(
            app,
            ["api", "request", "POST", "/api/v1/conversations", "--stdin", "--json"],
            input='{"title":"hi"}',
        )
    assert result.exit_code == 0, result.stdout
    assert json.loads(str(captured["body"])) == {"title": "hi"}


def test_api_request_4xx_exits_5(runner):
    """Non-2xx surfaces as ApiError -> exit 5."""
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=True) as r:
        r.get("/api/v1/nope").mock(return_value=httpx.Response(404, json={"detail": "missing"}))
        result = runner.invoke(app, ["api", "request", "GET", "/api/v1/nope"])
    assert result.exit_code == API_ERROR_EXIT_CODE


def test_api_request_header_parsing(runner):
    """-H 'K: V' propagates to the outgoing request."""
    _seed_persona()
    captured_headers: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json={"ok": True})

    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=True) as r:
        r.get("/api/v1/ping").mock(side_effect=_capture)
        result = runner.invoke(
            app,
            ["api", "request", "GET", "/api/v1/ping", "-H", "X-Trace: abc", "--json"],
        )
    assert result.exit_code == 0, result.stdout
    assert captured_headers.get("x-trace") == "abc"


def _openapi_doc() -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pawrrtal", "version": "0.1.0"},
        "paths": {
            "/api/v1/users/me": {"get": {"responses": {"200": {}}}},
            "/api/v1/conversations": {
                "get": {"responses": {"200": {}}},
                "post": {"responses": {"201": {}}},
            },
        },
    }


def test_api_openapi_json(runner):
    """`paw api openapi --json` returns the full schema."""
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=True) as r:
        r.get("/openapi.json").mock(return_value=httpx.Response(200, json=_openapi_doc()))
        result = runner.invoke(app, ["api", "openapi", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["info"]["title"] == "Pawrrtal"
    assert "/api/v1/users/me" in payload["paths"]


def test_api_ls_plain_lists_routes(runner):
    """`paw api ls --plain` emits TSV rows of METHOD\tPATH."""
    _seed_persona()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=True) as r:
        r.get("/openapi.json").mock(return_value=httpx.Response(200, json=_openapi_doc()))
        result = runner.invoke(app, ["api", "ls", "--plain"])
    assert result.exit_code == 0, result.stdout
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert "GET\t/api/v1/users/me" in lines
    assert "GET\t/api/v1/conversations" in lines
    assert "POST\t/api/v1/conversations" in lines
