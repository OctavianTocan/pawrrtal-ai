"""HTTP client for the paw persona — cookies in, structured errors out."""

from __future__ import annotations

import base64
import datetime as dt
import http.cookiejar
import json
import os
import sys
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import IO, Any

import httpx

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.errors import ApiError, AuthError, BackendUnreachable
from app.cli.paw.sse import stream_chat_events

DEFAULT_TIMEOUT_SECONDS = 60.0
RESPONSE_BODY_PREVIEW_BYTES = 500
ERROR_BODY_PREVIEW_CHARS = 200
HTTP_UNAUTHORIZED = 401

# Env var that, when set, triggers fixture recording inside PawClient.
# Set by `paw record` and inherited by the spawned/in-process command.
RECORD_ENV_VAR = "PAW_RECORD"


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
        record_path: str | os.PathLike[str] | None = None,
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
        # Recording: env var is the canonical trigger so `paw record` can
        # capture fixtures from any subcommand without threading the path
        # through every callsite.
        if record_path is None:
            record_path = os.environ.get(RECORD_ENV_VAR)
        self._record_path: Path | None = Path(record_path) if record_path else None
        self._record_file: IO[str] | None = None
        self._request_started: dict[int, float] = {}
        hooks: dict[str, list[Any]] = {"request": [], "response": []}
        if verbose:
            hooks["request"].append(self._log_request)
            hooks["response"].append(self._log_response)
        if self._record_path is not None:
            self._record_path.parent.mkdir(parents=True, exist_ok=True)
            self._record_file = self._record_path.open("a", encoding="utf-8")
            hooks["request"].append(self._record_request_start)
            hooks["response"].append(self._record_response)
        if hooks["request"] or hooks["response"]:
            self._client.event_hooks = hooks

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
            if self._record_file is not None:
                self._record_file.close()
                self._record_file = None

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

    async def _record_request_start(self, request: httpx.Request) -> None:
        """Stamp request start time so the matching response hook can compute duration."""
        self._request_started[id(request)] = time.perf_counter()

    async def _record_response(self, response: httpx.Response) -> None:
        """Append one JSONL row capturing the request + response pair.

        Streaming responses (``text/event-stream``) are tagged with
        ``is_stream=True`` and the response body is left empty here — the
        wire bytes are captured by the SSE consumer via :meth:`make_sse_tap`,
        which writes one ``type=sse`` row per frame between this envelope
        row and the consumer-emitted ``type=sse_done`` sentinel.
        """
        if self._record_file is None:
            return
        request = response.request
        started = self._request_started.pop(id(request), None)
        duration_ms = int((time.perf_counter() - started) * 1000) if started else 0
        content_type = response.headers.get("content-type", "")
        is_stream = "text/event-stream" in content_type
        body_text: str | None = None
        body_b64: str | None = None
        if not is_stream:
            await response.aread()
            try:
                body_text = response.content.decode("utf-8")
            except UnicodeDecodeError:
                body_b64 = base64.b64encode(response.content).decode("ascii")
        row = {
            "method": request.method,
            "url": str(request.url),
            "request_headers": dict(request.headers),
            "request_body": (
                request.content.decode("utf-8", errors="replace") if request.content else None
            ),
            "status": response.status_code,
            "response_headers": dict(response.headers),
            "response_body": body_text,
            "response_body_bytes_b64": body_b64,
            "is_stream": is_stream,
            "duration_ms": duration_ms,
        }
        # Single write keeps the line atomic relative to SIGKILL between
        # the JSON payload and the trailing newline — otherwise a crash
        # mid-row leaves a half-line that crashes `paw replay`'s JSON
        # decoder.
        self._record_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._record_file.flush()

    @property
    def is_recording(self) -> bool:
        """True when this client is capturing fixtures (``PAW_RECORD`` active)."""
        return self._record_file is not None

    def _write_record_row(self, row: dict[str, Any]) -> None:
        """Append a single JSONL row to the recording file (no-op if not recording).

        Concatenates the JSON payload with the trailing newline before
        the single ``write()`` so SIGKILL between the two cannot leave
        a truncated row that crashes downstream decoders.
        """
        if self._record_file is None:
            return
        self._record_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._record_file.flush()

    def record_sse_frame(self, method: str, url: str, frame: bytes) -> None:
        r"""Persist one raw SSE frame so `paw replay` can reconstruct the stream.

        ``frame`` is the bytes between two ``\n\n`` delimiters as observed
        by :func:`stream_chat_events`. The frame is base64-encoded to keep
        the row safe across any future non-UTF-8 producer. ``method`` is
        recorded so the replay layer can mount the response under the
        same (method, url) key the live consumer used — otherwise replay
        defaulted to POST and ignored GET-based streams.
        """
        self._write_record_row(
            {
                "type": "sse",
                "ts": dt.datetime.now(dt.UTC).isoformat(),
                "method": method,
                "url": url,
                "frame_b64": base64.b64encode(frame).decode("ascii"),
            }
        )

    def make_sse_tap(self, method: str, url: str) -> Callable[[bytes], None] | None:
        """Return a raw-frame tap for `stream_chat_events`, or None when off.

        Wires the SSE consumer to the recording file without leaking the
        recording mechanism into call sites: the consumer just passes the
        returned callable as ``on_raw_frame``. ``method`` is captured
        here so each recorded frame carries the verb the live consumer
        used.
        """
        if self._record_file is None:
            return None
        record_frame = self.record_sse_frame

        def tap(frame: bytes) -> None:
            record_frame(method, url, frame)

        return tap

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
                status_code=resp.status_code,
            )
        return resp

    def stream_events(
        self,
        *,
        method: str,
        url: str,
        json_body: Any | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield decoded SSE events for a chat endpoint, with recording wired in.

        Lets callers consume the chat stream without reaching into the
        private ``_client`` attribute. The recording tap is attached
        automatically when ``PAW_RECORD`` is active, so the call site
        only needs the URL + body. The returned async iterator delegates
        to :func:`app.cli.paw.sse.stream_chat_events`.
        """
        full_url = str(self._client.base_url.join(url))
        return stream_chat_events(
            self._client,
            method,
            url,
            json_body=json_body,
            on_raw_frame=self.make_sse_tap(method, full_url),
        )


@asynccontextmanager
async def open_client(state: PersonaState, *, verbose: bool = False) -> AsyncIterator[PawClient]:
    """Convenience context manager for one-off PawClient calls."""
    async with PawClient(state, verbose=verbose) as client:
        yield client
