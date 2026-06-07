"""Tests for LiteLLMLLM's StreamFn wiring into run_model_tool_loop.

Uses ``ScriptedStreamFn`` from ``tests.agent_loop_harness`` — no real
LiteLLM / OpenAI / xAI API calls are made.  These tests exercise the
provider's translation layer (AgentEvent → StreamEvent) and confirm
that history and prompts flow through the loop.  The text-only-v1
scope is also covered: ``tools`` must be accepted without crashing
(logged-and-ignored) and missing API keys must surface a clear error
through the StreamFn rather than an uncaught exception.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import litellm
import openai
import pytest
from litellm.exceptions import (
    AuthenticationError as LiteLLMAuthenticationError,
)
from litellm.exceptions import (
    BadRequestError as LiteLLMBadRequestError,
)
from litellm.exceptions import (
    RateLimitError as LiteLLMRateLimitError,
)
from litellm.exceptions import (
    Timeout as LiteLLMTimeout,
)
from litellm.exceptions import (
    UnsupportedParamsError as LiteLLMUnsupportedParamsError,
)

from app.agents.types import (
    AgentMessage,
    AgentTool,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    TextContent,
)
from app.providers._errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnknownError,
    ProviderUnsupportedParamError,
)
from app.providers.base import StreamEvent
from app.providers.litellm_provider import (
    LiteLLMLLM,
    _build_litellm_messages,
    _classify_litellm_exception,
    _litellm_model_string,
    open_litellm_stream,
)
from app.providers.model_id import Vendor
from tests.agent_loop_harness import ScriptedStreamFn, text_turn


@pytest.mark.anyio
async def test_litellm_provider_yields_delta_events_from_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiteLLMLLM.stream() translates run_model_tool_loop text_deltas to StreamEvent deltas."""
    provider = LiteLLMLLM("gpt-4o", Vendor.openai)
    monkeypatch.setattr(provider, "_stream_fn", ScriptedStreamFn([text_turn("hello")]))

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            question="Hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]

    delta_events = [e for e in events if e["type"] == "delta"]
    assert len(delta_events) >= 1
    assert any("hello" in e.get("content", "") for e in delta_events)


@pytest.mark.anyio
async def test_litellm_provider_passes_history_to_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prior messages in history are included in what the StreamFn sees."""
    seen_messages: list[list[AgentMessage]] = []

    async def recording_stream_fn(
        messages: list[AgentMessage], tools: list[AgentTool]
    ) -> AsyncIterator[LLMEvent]:
        seen_messages.append(list(messages))
        yield LLMTextDeltaEvent(type="text_delta", text="ok")
        yield LLMDoneEvent(
            type="done",
            stop_reason="stop",
            content=[TextContent(type="text", text="ok")],
        )

    provider = LiteLLMLLM("grok-3-latest", Vendor.xai)
    monkeypatch.setattr(provider, "_stream_fn", recording_stream_fn)

    history = [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]

    async for _ in provider.stream(
        question="And 3+3?",
        conversation_id=uuid4(),
        user_id=uuid4(),
        history=history,
    ):
        pass

    # Two history messages + the new prompt land in the loop together,
    # so the StreamFn sees three messages on its single LLM call.
    assert len(seen_messages) == 1
    assert len(seen_messages[0]) == 3


@pytest.mark.anyio
async def test_litellm_provider_accepts_tools_without_running_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1 ignores tools but must not crash when a non-empty list is passed."""

    async def _noop_execute(tool_call_id: str, **_kw: object) -> str:
        return "unused"

    tools = [
        AgentTool(
            name="noop",
            description="placeholder",
            parameters={"type": "object", "properties": {}},
            execute=_noop_execute,
        )
    ]

    provider = LiteLLMLLM("gpt-4o-mini", Vendor.openai)
    monkeypatch.setattr(provider, "_stream_fn", ScriptedStreamFn([text_turn("ok")]))

    events = [
        event
        async for event in provider.stream(
            question="Hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
            tools=tools,
        )
    ]
    # The scripted text turn still produces a delta — tools are dropped silently.
    assert any(e["type"] == "delta" for e in events)


def test_litellm_model_string_prefixes_vendor() -> None:
    assert _litellm_model_string(Vendor.openai, "gpt-4o") == "openai/gpt-4o"
    assert _litellm_model_string(Vendor.xai, "grok-3-latest") == "xai/grok-3-latest"


def test_build_litellm_messages_prepends_system_and_drops_tool_messages() -> None:
    history: list[AgentMessage] = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
            "stop_reason": "stop",
        },
    ]
    out = _build_litellm_messages(history, system_prompt="SYS")
    assert out[0] == {"role": "system", "content": "SYS"}
    assert {"role": "user", "content": "hi"} in out
    assert {"role": "assistant", "content": "hello"} in out


# ---------------------------------------------------------------------------
# Returns Phase 3 — ``open_litellm_stream`` + ``_classify_litellm_exception``.
#
# The returns pilot exposes the connection phase of a LiteLLM completion as a
# ``AsyncIterator[Any]`` (raises ``ProviderError`` on failure). These tests pin the
# SDK-exception → ProviderError mapping and the happy-path open. Mid-stream
# behaviour is still exception-driven and stays covered by the existing
# StreamFn/agent-loop tests above.
# ---------------------------------------------------------------------------


# A fake async iterator we can hand back from a patched ``acompletion``.
async def _fake_chunks() -> AsyncIterator[object]:
    yield object()


def _make_auth_error() -> LiteLLMAuthenticationError:
    return LiteLLMAuthenticationError(
        message="bad key",
        llm_provider="openai",
        model="gpt-4o",
    )


def _make_rate_limit_error() -> LiteLLMRateLimitError:
    return LiteLLMRateLimitError(
        message="slow down",
        llm_provider="openai",
        model="gpt-4o",
    )


def _make_unsupported_params_error() -> LiteLLMUnsupportedParamsError:
    err = LiteLLMUnsupportedParamsError(
        message="reasoning_effort not supported for gpt-4o",
        llm_provider="openai",
        model="gpt-4o",
    )
    # The SDK does not always populate ``param``; the classifier reads it
    # defensively. Set it here so the assertion below has something concrete.
    err.param = "reasoning_effort"
    return err


def _make_timeout_error() -> LiteLLMTimeout:
    return LiteLLMTimeout(
        message="deadline exceeded",
        llm_provider="openai",
        model="gpt-4o",
    )


def test_classify_litellm_exception_auth() -> None:
    err = _classify_litellm_exception(_make_auth_error(), model="openai/gpt-4o")
    assert isinstance(err, ProviderAuthError)
    assert "bad key" in err.message


def test_classify_litellm_exception_rate_limit() -> None:
    err = _classify_litellm_exception(_make_rate_limit_error(), model="openai/gpt-4o")
    assert isinstance(err, ProviderRateLimitError)
    # ``retry_after`` is best-effort; the SDK does not always populate it.
    assert err.retry_after is None or isinstance(err.retry_after, float)


def test_classify_litellm_exception_unsupported_param() -> None:
    err = _classify_litellm_exception(_make_unsupported_params_error(), model="openai/gpt-4o")
    assert isinstance(err, ProviderUnsupportedParamError)
    assert err.param == "reasoning_effort"
    assert err.model == "openai/gpt-4o"


def test_classify_litellm_exception_timeout() -> None:
    err = _classify_litellm_exception(_make_timeout_error(), model="openai/gpt-4o")
    assert isinstance(err, ProviderTimeoutError)


def test_classify_litellm_exception_unknown_fallback() -> None:
    err = _classify_litellm_exception(RuntimeError("boom"), model="openai/gpt-4o")
    assert isinstance(err, ProviderUnknownError)
    assert "boom" in err.message


@pytest.mark.anyio
async def test_open_litellm_stream_returns_iterator_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: returns the LiteLLM async iterator."""
    import app.providers.litellm_provider as mod

    iterator = _fake_chunks()

    async def _fake_acompletion(**_kwargs: object) -> AsyncIterator[object]:
        return iterator

    # Make API-key resolution deterministic without touching env / DB.
    monkeypatch.setattr(mod, "_resolve_litellm_api_key", lambda *_a, **_kw: "sk-test")
    monkeypatch.setattr(litellm, "acompletion", _fake_acompletion)

    result = await open_litellm_stream(
        Vendor.openai,
        "gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert result is iterator


@pytest.mark.anyio
async def test_open_litellm_stream_maps_auth_error_to_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LiteLLMAuthenticationError`` surfaces as raises ``ProviderAuthError``."""
    import app.providers.litellm_provider as mod

    async def _raise_auth(**_kwargs: object) -> AsyncIterator[object]:
        raise _make_auth_error()

    monkeypatch.setattr(mod, "_resolve_litellm_api_key", lambda *_a, **_kw: "sk-test")
    monkeypatch.setattr(litellm, "acompletion", _raise_auth)

    with pytest.raises(ProviderAuthError):
        await open_litellm_stream(
            Vendor.openai,
            "gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )


@pytest.mark.anyio
async def test_open_litellm_stream_maps_rate_limit_error_to_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LiteLLMRateLimitError`` surfaces as raises ``ProviderRateLimitError``."""
    import app.providers.litellm_provider as mod

    async def _raise_rate(**_kwargs: object) -> AsyncIterator[object]:
        raise _make_rate_limit_error()

    monkeypatch.setattr(mod, "_resolve_litellm_api_key", lambda *_a, **_kw: "sk-test")
    monkeypatch.setattr(litellm, "acompletion", _raise_rate)

    with pytest.raises(ProviderRateLimitError):
        await open_litellm_stream(
            Vendor.openai,
            "gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )


@pytest.mark.anyio
async def test_open_litellm_stream_maps_unsupported_param_to_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LiteLLMUnsupportedParamsError`` surfaces with ``param`` + ``model``."""
    import app.providers.litellm_provider as mod

    async def _raise_unsupported(**_kwargs: object) -> AsyncIterator[object]:
        raise _make_unsupported_params_error()

    monkeypatch.setattr(mod, "_resolve_litellm_api_key", lambda *_a, **_kw: "sk-test")
    monkeypatch.setattr(litellm, "acompletion", _raise_unsupported)

    with pytest.raises(ProviderUnsupportedParamError) as excinfo:
        await open_litellm_stream(
            Vendor.openai,
            "gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
    inner = excinfo.value
    assert inner.param == "reasoning_effort"
    assert inner.model == "openai/gpt-4o-mini"


@pytest.mark.anyio
async def test_open_litellm_stream_missing_key_is_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing API key collapses into ``ProviderAuthError`` (single match arm)."""
    import app.providers.litellm_provider as mod

    monkeypatch.setattr(mod, "_resolve_litellm_api_key", lambda *_a, **_kw: None)

    with pytest.raises(ProviderAuthError):
        await open_litellm_stream(
            Vendor.openai,
            "gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )


# ---------------------------------------------------------------------------
# Regression coverage — the LiteLLM exception hierarchy puts every HTTP error
# subclass under ``openai.APIError`` (NOT ``litellm.exceptions.APIError``),
# so the safety-net catch tuple must include ``openai.APIError`` for those
# subclasses to be classified rather than propagate raw. Without these tests
# the bug returned silently the moment anyone "tidied up" the import block.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_open_litellm_stream_with_litellm_bad_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``BadRequestError`` (a subclass of ``openai.APIError``) routes to ``ProviderUnknownError``.

    Before the catch-tuple fix this raised raw out of ``FutureResult`` because
    ``litellm.BadRequestError`` does not inherit from ``litellm.APIError``.
    """
    import app.providers.litellm_provider as mod

    async def _raise_bad_request(**_kwargs: object) -> AsyncIterator[object]:
        raise LiteLLMBadRequestError(
            message="bad request body",
            llm_provider="openai",
            model="gpt-4o-mini",
        )

    monkeypatch.setattr(mod, "_resolve_litellm_api_key", lambda *_a, **_kw: "sk-test")
    monkeypatch.setattr(litellm, "acompletion", _raise_bad_request)

    with pytest.raises(ProviderUnknownError) as excinfo:
        await open_litellm_stream(
            Vendor.openai,
            "gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
    inner = excinfo.value
    assert "bad request body" in inner.message


def test_classify_litellm_exception_with_openai_apiconnection_error() -> None:
    """``openai.APIConnectionError`` (LiteLLM's transient network parent) → ``ProviderUnknownError``.

    Confirms the upstream ``openai.APIError`` base catches everything LiteLLM
    inherits from it. Without the broadened catch tuple this would have
    escaped the classifier entirely.
    """
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    exc = openai.APIConnectionError(message="connection reset", request=request)
    err = _classify_litellm_exception(exc, model="openai/gpt-4o")
    assert isinstance(err, ProviderUnknownError)
    assert "connection reset" in err.message


def test_classify_litellm_exception_rate_limit_parses_retry_after_from_header() -> None:
    """``Retry-After`` on the upstream response surfaces on ``ProviderRateLimitError``.

    LiteLLM's ``RateLimitError.__init__`` does not set a ``retry_after``
    attribute — the actual hint lives on ``exc.response.headers``. This test
    pins the header-parsing path that replaced the previously dead
    ``getattr(exc, "retry_after", None)`` lookup.
    """
    response = httpx.Response(
        status_code=429,
        headers={"Retry-After": "42"},
    )
    exc = LiteLLMRateLimitError(
        message="slow down",
        llm_provider="openai",
        model="gpt-4o",
        response=response,
    )
    err = _classify_litellm_exception(exc, model="openai/gpt-4o")
    assert isinstance(err, ProviderRateLimitError)
    assert err.retry_after == 42.0


def test_classify_litellm_exception_rate_limit_ignores_non_numeric_retry_after() -> None:
    """Non-numeric ``Retry-After`` values (HTTP date format) degrade to ``None``."""
    response = httpx.Response(
        status_code=429,
        headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
    )
    exc = LiteLLMRateLimitError(
        message="slow down",
        llm_provider="openai",
        model="gpt-4o",
        response=response,
    )
    err = _classify_litellm_exception(exc, model="openai/gpt-4o")
    assert isinstance(err, ProviderRateLimitError)
    assert err.retry_after is None


@pytest.mark.anyio
async def test_open_litellm_stream_unmapped_vendor_returns_provider_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vendors not in ``_VENDOR_API_KEY_NAME`` degrade gracefully instead of raising ``KeyError``.

    ``Vendor.deepseek`` (and friends) have no entry in the env-var map yet,
    so the missing-key branch used to crash on ``_VENDOR_API_KEY_NAME[vendor]``
    while constructing the user-facing error. The fallback to ``vendor.value``
    keeps the message readable; the broadened catch tuple also catches the
    raw ``KeyError`` as a belt-and-braces safety net.
    """
    import app.providers.litellm_provider as mod

    monkeypatch.setattr(mod, "_resolve_litellm_api_key", lambda *_a, **_kw: None)

    with pytest.raises(ProviderAuthError) as excinfo:
        await open_litellm_stream(
            Vendor.deepseek,
            "deepseek-chat",
            messages=[{"role": "user", "content": "hi"}],
        )
    inner = excinfo.value
    assert "deepseek" in inner.message
