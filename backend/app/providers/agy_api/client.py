"""Direct Cloud Code Assist request/stream parsing for Antigravity."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.agents.types import (
    AgentMessage,
    AgentTool,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    TextContent,
)
from app.providers.base import StreamEvent

from .auth import AgyApiAuth, AgyApiAuthError
from .events import (
    AgyApiStreamState,
    AgyApiUsageAccumulator,
    build_done_event,
    llm_events_from_response,
    stream_event_from_response,
)
from .messages import build_agy_contents, build_agy_tool_declarations

_DEFAULT_BASE_URL = "https://daily-cloudcode-pa.googleapis.com"
_HTTP_TIMEOUT_SECONDS = 60.0
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_BAD_REQUEST = 400
_HTTP_MAX_CONNECTIONS = 20
_HTTP_MAX_KEEPALIVE_CONNECTIONS = 10


@dataclass
class _ClientCache:
    client: httpx.AsyncClient | None = None


class AgyApiRemoteAuthError(AgyApiAuthError):
    """Raised when Cloud Code Assist rejects the current local AGY token."""


_CLIENT_CACHE = _ClientCache()


def build_generate_body(
    *,
    auth: AgyApiAuth,
    model_id: str,
    question: str,
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
    tools: list[AgentTool] | None = None,
    generation_config: dict[str, Any] | None = None,
    contents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the Cloud Code Assist Gemini-style generation envelope."""
    request: dict[str, Any] = {
        "contents": contents if contents is not None else _build_contents(history, question),
        "generationConfig": generation_config or {},
    }
    tool_declarations = build_agy_tool_declarations(tools or [])
    if tool_declarations is not None:
        request["tools"] = tool_declarations
    body: dict[str, Any] = {
        "project": auth.project_id,
        "model": model_id,
        "request": request,
        "requestType": "chat",
        "userAgent": "antigravity",
        "requestId": f"pawrrtal-{uuid.uuid4()}",
    }
    if system_prompt and system_prompt.strip():
        body["request"]["systemInstruction"] = {
            "parts": [{"text": system_prompt.strip()}],
        }
    return body


async def stream_llm_events(
    *,
    auth: AgyApiAuth,
    model_id: str,
    messages: list[AgentMessage],
    system_prompt: str | None,
    tools: list[AgentTool],
    generation_config: dict[str, Any],
    usage_sink: AgyApiUsageAccumulator,
) -> AsyncIterator[LLMEvent]:
    """Stream Antigravity chunks as provider-neutral agent-loop events."""
    body = build_generate_body(
        auth=auth,
        model_id=model_id,
        question="",
        history=None,
        system_prompt=system_prompt,
        tools=tools,
        generation_config=generation_config,
        contents=build_agy_contents(messages),
    )
    state = AgyApiStreamState()
    async for event in _stream_llm_events_from_body(auth=auth, body=body, state=state):
        yield event
    usage_sink.absorb_request(state.last_usage_metadata)
    yield build_done_event(state)


async def stream_generate_content(
    *,
    auth: AgyApiAuth,
    model_id: str,
    question: str,
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
) -> AsyncIterator[StreamEvent]:
    """Stream text deltas from Antigravity's Cloud Code Assist endpoint."""
    headers = _headers(auth.access_token)
    body = build_generate_body(
        auth=auth,
        model_id=model_id,
        question=question,
        history=history,
        system_prompt=system_prompt,
    )
    try:
        client = _client()
        async with client.stream(
            "POST",
            f"{_base_url()}/v1internal:streamGenerateContent?alt=sse",
            headers=headers,
            json=body,
        ) as response:
            error_text = await _api_error_text(response)
            if error_text is not None:
                yield _error_event(error_text)
                return
            async for event in _stream_events_from_response(response):
                yield event
    except httpx.RequestError as exc:
        yield _error_event(f"Antigravity API request failed: {exc.__class__.__name__}: {exc}")
        return


async def _stream_llm_events_from_body(
    *,
    auth: AgyApiAuth,
    body: dict[str, Any],
    state: AgyApiStreamState,
) -> AsyncIterator[LLMEvent]:
    try:
        client = _client()
        async with client.stream(
            "POST",
            f"{_base_url()}/v1internal:streamGenerateContent?alt=sse",
            headers=_headers(auth.access_token),
            json=body,
        ) as response:
            await _raise_for_remote_auth_error(response)
            error_text = await _api_error_text(response)
            if error_text is not None:
                yield _error_text_delta(error_text)
                yield _error_text_done(error_text)
                return
            async for event in _llm_events_from_response(response, state):
                yield event
    except httpx.RequestError as exc:
        error_text = f"Antigravity API request failed: {exc.__class__.__name__}: {exc}"
        yield _error_text_delta(error_text)
        yield _error_text_done(error_text)
        return


def _error_text_delta(message: str) -> LLMTextDeltaEvent:
    return LLMTextDeltaEvent(type="text_delta", text=message)


def _error_text_done(message: str) -> LLMDoneEvent:
    return LLMDoneEvent(
        type="done",
        stop_reason="error",
        content=[TextContent(type="text", text=message)],
    )


async def _api_error_text(response: httpx.Response) -> str | None:
    """Return the short API error body for non-2xx stream responses."""
    if response.status_code < _HTTP_BAD_REQUEST:
        return None
    text = await response.aread()
    return f"Antigravity API returned {response.status_code}: {text.decode(errors='replace')[:300]}"


async def _raise_for_remote_auth_error(response: httpx.Response) -> None:
    """Raise before a normal auth-refresh case becomes assistant text."""
    if response.status_code not in {_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN}:
        return
    text = await response.aread()
    preview = text.decode(errors="replace")[:300]
    raise AgyApiRemoteAuthError(
        f"Antigravity API rejected the local token with {response.status_code}: {preview}"
    )


async def _stream_events_from_response(response: httpx.Response) -> AsyncIterator[StreamEvent]:
    """Yield provider-neutral stream events from an SSE response."""
    async for line in response.aiter_lines():
        event = _event_from_sse_line(line)
        if event is not None:
            yield event


async def _llm_events_from_response(
    response: httpx.Response,
    state: AgyApiStreamState,
) -> AsyncIterator[LLMEvent]:
    """Yield agent-loop events from an Antigravity SSE response."""
    async for line in response.aiter_lines():
        data = _json_from_sse_line(line)
        if data is None:
            continue
        response_body = data.get("response", data)
        for event in llm_events_from_response(response_body, state):
            yield event


def _client() -> httpx.AsyncClient:
    """Return a warm shared HTTP client for direct Antigravity API calls."""
    if _CLIENT_CACHE.client is None or _CLIENT_CACHE.client.is_closed:
        _CLIENT_CACHE.client = httpx.AsyncClient(
            http2=True,
            timeout=_HTTP_TIMEOUT_SECONDS,
            limits=httpx.Limits(
                max_connections=_HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=_HTTP_MAX_KEEPALIVE_CONNECTIONS,
            ),
        )
    return _CLIENT_CACHE.client


async def close_agy_api_client() -> None:
    """Close the shared Antigravity API HTTP client."""
    client = _CLIENT_CACHE.client
    _CLIENT_CACHE.client = None
    if client is not None and not client.is_closed:
        await client.aclose()


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "antigravity",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": json.dumps(
            {"ideType": "ANTIGRAVITY", "platform": "LINUX", "pluginType": "GEMINI"}
        ),
    }


def _base_url() -> str:
    """Return the Cloud Code Assist base URL used by this ``agy`` build."""
    return os.getenv("AGY_API_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _build_contents(
    history: list[dict[str, str]] | None,
    question: str,
) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for item in history or []:
        role = item.get("role")
        text = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )
    contents.append({"role": "user", "parts": [{"text": question}]})
    return contents


def _event_from_sse_line(line: str) -> StreamEvent | None:
    data = _json_from_sse_line(line)
    if data is None:
        return None
    response = data.get("response", data)
    return _stream_event_from_response(response)


def _json_from_sse_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    payload = line.removeprefix("data:").strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _stream_event_from_response(response: object) -> StreamEvent | None:
    return stream_event_from_response(response)


def _extract_text(response: object) -> str:
    if not isinstance(response, dict):
        return ""
    candidates = response.get("candidates")
    if not isinstance(candidates, list):
        return ""
    chunks: list[str] = []
    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        chunks.extend(
            part["text"]
            for part in parts
            if (
                isinstance(part, dict)
                and part.get("thought") is not True
                and isinstance(part.get("text"), str)
            )
        )
    return "".join(chunks)


def _extract_thinking(response: object) -> str:
    if not isinstance(response, dict):
        return ""
    candidates = response.get("candidates")
    if not isinstance(candidates, list):
        return ""
    chunks: list[str] = []
    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        chunks.extend(
            part["text"]
            for part in parts
            if (
                isinstance(part, dict)
                and part.get("thought") is True
                and isinstance(part.get("text"), str)
                and part["text"]
            )
        )
    return "".join(chunks)


def _extract_usage(response: object) -> StreamEvent | None:
    if not isinstance(response, dict):
        return None
    usage = response.get("usageMetadata")
    if not isinstance(usage, dict):
        return None
    input_tokens = int(usage.get("promptTokenCount") or 0)
    output_tokens = int(usage.get("candidatesTokenCount") or 0)
    if input_tokens == 0 and output_tokens == 0:
        return None
    return StreamEvent(
        type="usage",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.0,
    )


def _error_event(message: str) -> StreamEvent:
    return StreamEvent(type="error", content=message)
