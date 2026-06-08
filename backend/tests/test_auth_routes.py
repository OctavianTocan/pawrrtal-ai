"""Tests for the canonical and compat auth/users mounts.

Covers the gaps surfaced by paw:

- ``/api/v1/users/me`` is the canonical v1 path and ``/users/me`` is the
  thin compat alias kept for the frontend (pawrrtal-kp50, Gap 2).
- ``POST /auth/jwt/logout`` is mounted by ``fastapi_users.get_auth_router``
  and so paw can call it to revoke the server-side cookie
  (pawrrtal-kp50, Gap 3).

Auth-runtime behaviour of these routes (issuing a real JWT, validating
cookies, etc.) is owned by fastapi-users' own test suite — these tests
only verify our mount surface so the wire contract paw consumes stays
stable.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import Response

from app.infrastructure.auth.dev_login import _redirect_with_login_cookie, _safe_redirect_path
from main import create_app


def _route_methods(app: FastAPI, path: str) -> set[str]:
    """Return the union of HTTP methods registered at ``path``.

    fastapi-users registers each verb as its own ``APIRoute`` (one route
    for ``GET /users/me``, a sibling for ``PATCH /users/me``), so we walk
    every route at the path and merge the method sets. Returns an empty
    set when the path is not mounted.
    """
    methods: set[str] = set()
    for route in app.routes:
        if getattr(route, "path", None) == path:
            methods.update(getattr(route, "methods", None) or set())
    return methods


@pytest.fixture
def mounted_app() -> FastAPI:
    """Build the app for route-table assertions without database fixtures."""
    return create_app()


class TestUsersMount:
    """The fastapi-users user router is mounted at two prefixes.

    The canonical mount (``/api/v1/users``) matches every other v1 route;
    the legacy ``/users`` mount is preserved as a compat alias so the
    existing frontend keeps working until it migrates.
    """

    @pytest.mark.anyio
    async def test_canonical_v1_users_me_is_mounted(self, mounted_app: FastAPI) -> None:
        assert "GET" in _route_methods(mounted_app, "/api/v1/users/me")
        assert "PATCH" in _route_methods(mounted_app, "/api/v1/users/me")

    @pytest.mark.anyio
    async def test_legacy_users_me_alias_is_mounted(self, mounted_app: FastAPI) -> None:
        assert "GET" in _route_methods(mounted_app, "/users/me")
        assert "PATCH" in _route_methods(mounted_app, "/users/me")

    @pytest.mark.anyio
    async def test_canonical_and_alias_expose_same_methods(self, mounted_app: FastAPI) -> None:
        # If the two mounts ever drift, paw (canonical) and the frontend
        # (alias) would see divergent surfaces — guard against that.
        canonical = _route_methods(mounted_app, "/api/v1/users/me")
        alias = _route_methods(mounted_app, "/users/me")
        assert canonical == alias


class TestAuthLogoutRoute:
    """``POST /auth/jwt/logout`` is exposed by ``get_auth_router``.

    The route comes from ``fastapi_users.get_auth_router(backend=auth_backend)``
    — we just confirm it's wired up so a future change to the backend's
    auth-router widening doesn't silently drop the endpoint paw relies on.
    """

    @pytest.mark.anyio
    async def test_logout_route_is_mounted(self, mounted_app: FastAPI) -> None:
        assert "POST" in _route_methods(mounted_app, "/auth/jwt/logout")

    @pytest.mark.anyio
    async def test_login_route_is_mounted(self, mounted_app: FastAPI) -> None:
        # Sanity check — the pair (login + logout) is what paw drives.
        assert "POST" in _route_methods(mounted_app, "/auth/jwt/login")

    @pytest.mark.anyio
    async def test_dev_login_route_is_mounted(self, mounted_app: FastAPI) -> None:
        assert "POST" in _route_methods(mounted_app, "/auth/dev-login")
        assert "POST" in _route_methods(mounted_app, "/auth/dev-login/browser")


class TestDevLoginRoute:
    """Dev-login supports API callers and pre-hydration browser form fallback."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("/", "/"),
            ("/settings?tab=dev", "/settings?tab=dev"),
            ("https://example.invalid/steal", "/"),
            ("//example.invalid/steal", "/"),
            ("\\settings", "/"),
            (None, "/"),
        ],
    )
    def test_safe_redirect_path_keeps_dev_login_local(
        self,
        value: object,
        expected: str,
    ) -> None:
        assert _safe_redirect_path(value) == expected

    def test_redirect_with_login_cookie_carries_session_cookie(self) -> None:
        login_response = Response(status_code=204)
        login_response.set_cookie("session_token", "test-session", httponly=True)

        response = _redirect_with_login_cookie(login_response, "/settings")

        assert response.status_code == 303
        assert response.headers["location"] == "/settings"
        assert "session_token=test-session" in response.headers.get("set-cookie", "")
