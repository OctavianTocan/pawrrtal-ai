"""HTTP client for the paw persona — cookies in, structured errors out."""

from __future__ import annotations

import http.cookiejar
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.errors import ApiError, AuthError, BackendUnreachable

DEFAULT_TIMEOUT_SECONDS = 60.0
RESPONSE_BODY_PREVIEW_BYTES = 500
ERROR_BODY_PREVIEW_CHARS = 200
HTTP_UNAUTHORIZED = 401


def load_cookies(path: Path) -> http.cookiejar.MozillaCookieJar:
    """Load a Mozilla cookie jar from disk; returns an empty jar if missing.

    Use a real cookie jar so Set-Cookie headers with ``Expires=...,GMT`` (commas
    in date values) round-trip intact. Never regex-parse Set-Cookie strings.
    """
    jar = http.cookiejar.MozillaCookieJar(str(path))
    if path.exists():
        jar.load(ignore_discard=True, ignore_expires=True)
    return jar


def save_cookies(jar: http.cookiejar.CookieJar, path: Path) -> None:
    """Persist the cookie jar in Mozilla format and chmod 0600.

    Cookies are sensitive (session bearer tokens); restrict file permissions.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(jar, http.cookiejar.MozillaCookieJar):
        jar.filename = str(path)
        jar.save(ignore_discard=True, ignore_expires=True)
    else:
        moz = http.cookiejar.MozillaCookieJar(str(path))
        for c in jar:
            moz.set_cookie(c)
        moz.save(ignore_discard=True, ignore_expires=True)
    path.chmod(0o600)


class PawClient:
    """httpx.AsyncClient wrapper carrying the persona's cookie jar + base URL.

    Errors map to paw exit codes:

    - ``httpx.ConnectError`` -> ``BackendUnreachable`` (exit 4)
    - HTTP 401              -> ``AuthError`` (exit 3)
    - Other 4xx/5xx         -> ``ApiError`` (exit 5)
    """

    def __init__(
        self,
        state: PersonaState,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        verbose: bool = False,
    ) -> None:
        self._state = state
        self._verbose = verbose
        self._jar = load_cookies(cookies_path(state.profile))
        self._client = httpx.AsyncClient(
            base_url=state.api_base_url,
            cookies=self._jar,
            timeout=timeout,
            follow_redirects=False,
        )
        if verbose:
            self._client.event_hooks = {
                "request": [self._log_request],
                "response": [self._log_response],
            }

    @property
    def jar(self) -> http.cookiejar.CookieJar:
        """Return the live cookie jar (mutated by every response)."""
        return self._jar

    async def __aenter__(self) -> PawClient:
        """Enter the async context (no-op; client is constructed in __init__)."""
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Persist cookies on exit, then close the underlying httpx client."""
        try:
            save_cookies(self._jar, cookies_path(self._state.profile))
        finally:
            await self._client.aclose()

    async def _log_request(self, request: httpx.Request) -> None:
        """Stream a curl-like trace of the outgoing request to stderr."""
        sys.stderr.write(f"> {request.method} {request.url}\n")
        for k, v in request.headers.items():
            sys.stderr.write(f"> {k}: {v}\n")
        if request.content:
            body = request.content.decode("utf-8", errors="replace")
            sys.stderr.write(f"> \n> {body}\n")

    async def _log_response(self, response: httpx.Response) -> None:
        """Stream a curl-like trace of the incoming response to stderr."""
        await response.aread()
        sys.stderr.write(f"< {response.status_code} {response.reason_phrase}\n")
        for k, v in response.headers.items():
            sys.stderr.write(f"< {k}: {v}\n")
        if response.content:
            body = response.content.decode("utf-8", errors="replace")
            sys.stderr.write(f"< \n< {body[:RESPONSE_BODY_PREVIEW_BYTES]}\n")

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect: tuple[int, ...] = (200,),
    ) -> httpx.Response:
        """Issue an HTTP request and map transport/HTTP failures to PawError types."""
        try:
            resp = await self._client.request(
                method,
                path,
                json=json_body,
                data=data,
                params=params,
                headers=headers,
            )
        except httpx.ConnectError as e:
            raise BackendUnreachable(
                f"Cannot reach backend at {self._state.api_base_url}: {e}",
            ) from e
        if resp.status_code == HTTP_UNAUTHORIZED:
            raise AuthError("Session expired or missing.")
        if expect and resp.status_code not in expect:
            raise ApiError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:ERROR_BODY_PREVIEW_CHARS]}",
            )
        return resp


@asynccontextmanager
async def open_client(state: PersonaState, *, verbose: bool = False) -> AsyncIterator[PawClient]:
    """Convenience context manager for one-off PawClient calls."""
    async with PawClient(state, verbose=verbose) as client:
        yield client
