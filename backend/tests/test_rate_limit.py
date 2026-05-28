"""Tests for the in-memory chat rate-limit middleware."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.infrastructure.middleware.rate_limit import (
    CHAT_PATH_PREFIX,
    ChatRateLimitMiddleware,
    InMemoryWindow,
    reset_rate_limit_storage_for_tests,
)


def _build_app() -> Starlette:
    """Minimal Starlette app exercising the middleware in isolation.

    We don't pull up the whole FastAPI stack so the test stays focused
    on the middleware semantics (window math, identity extraction,
    response shape) without dragging in auth + DB setup.
    """

    async def _chat(request):
        return JSONResponse({"ok": True})

    async def _other(request):
        return JSONResponse({"ok": True, "endpoint": "other"})

    app = Starlette(
        routes=[
            Route(f"{CHAT_PATH_PREFIX}/", _chat, methods=["POST"]),
            Route("/api/v1/other", _other, methods=["GET"]),
        ],
    )
    app.add_middleware(ChatRateLimitMiddleware)
    return app


@pytest.fixture(autouse=True)
def _reset_storage():
    """Per-test isolation so windows from one case don't leak into the next."""
    reset_rate_limit_storage_for_tests()
    yield
    reset_rate_limit_storage_for_tests()


def test_disabled_when_limit_is_zero() -> None:
    """The middleware short-circuits when the configured limit is 0."""
    with patch("app.core.rate_limit.settings") as mock_settings:
        mock_settings.chat_rate_limit_per_minute = 0
        with TestClient(_build_app()) as client:
            for _ in range(50):
                response = client.post(
                    f"{CHAT_PATH_PREFIX}/",
                    cookies={"session_token": "fake.jwt.value"},
                )
                assert response.status_code == 200


def test_non_chat_routes_are_never_limited() -> None:
    """Even with the limit set to 1, non-chat paths fall straight through."""
    with patch("app.core.rate_limit.settings") as mock_settings:
        mock_settings.chat_rate_limit_per_minute = 1
        with TestClient(_build_app()) as client:
            for _ in range(5):
                response = client.get(
                    "/api/v1/other",
                    cookies={"session_token": "fake.jwt.value"},
                )
                assert response.status_code == 200


def test_anonymous_request_is_passed_through() -> None:
    """No session cookie → not our problem; auth dep on the route returns 401."""
    with patch("app.core.rate_limit.settings") as mock_settings:
        mock_settings.chat_rate_limit_per_minute = 1
        with TestClient(_build_app()) as client:
            for _ in range(5):
                response = client.post(f"{CHAT_PATH_PREFIX}/")  # no cookie
                assert response.status_code == 200


def test_returns_429_after_the_limit_is_exceeded() -> None:
    """The first 3 requests pass; the 4th gets a structured 429."""
    with patch("app.core.rate_limit.settings") as mock_settings:
        mock_settings.chat_rate_limit_per_minute = 3
        cookies = {"session_token": "tavi.session.jwt"}
        with TestClient(_build_app()) as client:
            for _ in range(3):
                assert client.post(f"{CHAT_PATH_PREFIX}/", cookies=cookies).status_code == 200
            blocked = client.post(f"{CHAT_PATH_PREFIX}/", cookies=cookies)

    assert blocked.status_code == 429
    body = blocked.json()
    assert body["limit"] == 3
    assert "retry_after_seconds" in body
    assert body["retry_after_seconds"] >= 1
    assert blocked.headers["Retry-After"] == str(body["retry_after_seconds"])


def test_separate_users_have_independent_windows() -> None:
    """One user's saturation must not affect another."""
    with patch("app.core.rate_limit.settings") as mock_settings:
        mock_settings.chat_rate_limit_per_minute = 2
        with TestClient(_build_app()) as client:
            # Tavi hits the limit.
            tavi = {"session_token": "tavi.jwt"}
            assert client.post(f"{CHAT_PATH_PREFIX}/", cookies=tavi).status_code == 200
            assert client.post(f"{CHAT_PATH_PREFIX}/", cookies=tavi).status_code == 200
            assert client.post(f"{CHAT_PATH_PREFIX}/", cookies=tavi).status_code == 429
            # Esther is unaffected.
            esther = {"session_token": "esther.jwt"}
            assert client.post(f"{CHAT_PATH_PREFIX}/", cookies=esther).status_code == 200


def test_in_memory_window_trims_to_window_size() -> None:
    """Direct unit test on the storage class — count returns only recent entries."""
    storage = InMemoryWindow()
    # Three timestamps spaced 1 s apart.
    storage.record_and_count("k", now=100.0, window=60.0)
    storage.record_and_count("k", now=101.0, window=60.0)
    count, oldest = storage.record_and_count("k", now=102.0, window=60.0)
    assert count == 3
    assert oldest == pytest.approx(100.0)
    # Now jump forward past the window.  All previous entries should be trimmed
    # on the next call.
    count, oldest = storage.record_and_count("k", now=200.0, window=60.0)
    assert count == 1
    assert oldest == pytest.approx(200.0)
