"""API tests for chat streaming routes."""

from collections.abc import AsyncIterator, Callable
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.agents.types import AgentSafetyConfig
from app.models import Workspace  # used via fixture type hint
from app.providers.base import AILLM
from app.providers.selection import ProviderSelection
from tests.agent_loop_harness import ScriptedStreamFn, echo_tool, text_turn, tool_call_turn


def _select_provider(provider: object) -> Callable[..., ProviderSelection]:
    """Return a turn-pipeline provider selector for ``provider``."""

    def _require_provider(model_id: str, **_kwargs: object) -> ProviderSelection:
        return ProviderSelection(provider=cast(AILLM, provider), effective_model_id=model_id)

    return _require_provider


class FakeProvider:
    """Provider test double that yields configured stream events."""

    def __init__(self, events: list[dict[str, str]]) -> None:
        self.events = events

    async def stream(
        self,
        question: str,
        conversation_id: object,
        user_id: object,
        history: object = None,
        tools: object = None,
        system_prompt: object = None,
        reasoning_effort: object = None,
        images: object = None,
    ) -> AsyncIterator[dict[str, str]]:
        for event in self.events:
            yield event


@pytest.mark.anyio
async def test_chat_returns_404_for_missing_conversation(client: AsyncClient) -> None:
    """Chat requests require an existing owned conversation."""
    response = await client.post(
        "/api/v1/chat/",
        json={"question": "hello", "conversation_id": str(uuid4())},
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_chat_returns_412_when_user_has_no_workspace(
    client: AsyncClient,
) -> None:
    """Chat refuses to run before onboarding is complete.

    No ``seeded_default_workspace`` fixture here — the user hasn't been
    onboarded yet, so the API must return 412 Precondition Failed rather
    than silently running with degraded tools.
    """
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "NoWS"})

    # Supply a model so the request clears the model_id requirement (422)
    # and actually reaches the workspace precondition check (412).
    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hello",
            "conversation_id": str(conversation_id),
            "model_id": "claude-code-pty:anthropic/claude-opus-4-7",
        },
    )

    assert response.status_code == 412
    assert "onboarding" in response.json()["detail"].lower()


@pytest.mark.anyio
async def test_chat_streams_provider_events(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """Chat streams provider events as SSE frames and terminates with DONE."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Chat"})
    monkeypatch.setattr(
        "app.turns.pipeline.prepare.require_provider",
        _select_provider(FakeProvider([{"type": "delta", "content": "hello"}])),
    )

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hello",
            "conversation_id": str(conversation_id),
            "model_id": "claude-code-pty:anthropic/claude-opus-4-7",
        },
    )

    assert response.status_code == 200
    assert 'data: {"type": "delta", "content": "hello"}' in response.text
    assert "data: [DONE]" in response.text


@pytest.mark.anyio
async def test_chat_persists_user_and_finalized_assistant_messages(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """Web chat persists both sides of a successful streaming turn."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Chat"})
    monkeypatch.setattr(
        "app.turns.pipeline.prepare.require_provider",
        _select_provider(FakeProvider([{"type": "delta", "content": "hello"}])),
    )

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hello",
            "conversation_id": str(conversation_id),
            "model_id": "claude-code-pty:anthropic/claude-opus-4-7",
        },
    )
    messages_response = await client.get(f"/api/v1/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    assert "data: [DONE]" in response.text
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"
    assert messages[0]["assistant_status"] is None
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "hello"
    assert messages[1]["assistant_status"] == "complete"


@pytest.mark.anyio
async def test_chat_forwards_reasoning_effort(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """Chat forwards the selected reasoning level to the provider."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Reasoning"})
    captured: dict[str, object] = {}

    class CapturingProvider(FakeProvider):
        async def stream(
            self,
            question: str,
            conversation_id: object,
            user_id: object,
            history: object = None,
            tools: object = None,
            system_prompt: object = None,
            reasoning_effort: object = None,
            images: object = None,
        ) -> AsyncIterator[dict[str, str]]:
            captured["reasoning_effort"] = reasoning_effort
            async for event in super().stream(
                question,
                conversation_id,
                user_id,
                history=history,
                tools=tools,
                system_prompt=system_prompt,
                reasoning_effort=reasoning_effort,
                images=images,
            ):
                yield event

    monkeypatch.setattr(
        "app.turns.pipeline.prepare.require_provider",
        _select_provider(CapturingProvider([{"type": "delta", "content": "ok"}])),
    )

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hello",
            "conversation_id": str(conversation_id),
            "model_id": "claude-code-pty:anthropic/claude-opus-4-7",
            "reasoning_effort": "extra-high",
        },
    )

    assert response.status_code == 200
    assert captured["reasoning_effort"] == "extra-high"


@pytest.mark.anyio
async def test_chat_persists_requested_model_id(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """Chat stores the requested model on the conversation."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Model"})
    monkeypatch.setattr(
        "app.turns.pipeline.prepare.require_provider",
        _select_provider(FakeProvider([{"type": "delta", "content": "ok"}])),
    )

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hello",
            "conversation_id": str(conversation_id),
            "model_id": "google/gemini-3-flash-preview",
        },
    )
    conversation_response = await client.get(f"/api/v1/conversations/{conversation_id}")

    assert response.status_code == 200
    # Pydantic canonicalises the request's bare ``vendor/model`` form into
    # the fully-qualified ``host:vendor/model`` wire shape before it
    # reaches the chat handler; the same canonical value is what gets
    # persisted onto the conversation row.
    assert conversation_response.json()["model_id"] == "google-ai:google/gemini-3-flash-preview"


@pytest.mark.anyio
async def test_chat_422_when_no_model_id_given(
    client: AsyncClient,
    seeded_default_workspace: Workspace,
) -> None:
    """A model_id is now required — no catalog-default fallback.

    When neither the request body nor the conversation row supplies a
    ``model_id``, the chat handler rejects the turn with 422 rather than
    silently resolving the catalog default.  This guards the new contract
    where "the default model" is no longer chosen implicitly on the API
    path; the caller must name a model.
    """
    # Create the conversation without a ``model_id`` so the row has none.
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "NoModel"})

    # No model_id in the body, and the conversation row has none either,
    # so the handler must refuse with 422.
    response = await client.post(
        "/api/v1/chat/",
        json={"question": "hello", "conversation_id": str(conversation_id)},
    )

    assert response.status_code == 422
    assert "model_id is required" in response.json()["detail"]


@pytest.mark.anyio
async def test_chat_stream_converts_provider_exception_to_error_event(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """Provider exceptions are emitted as stream-level error events."""
    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Error"})

    class FailingProvider:
        async def stream(
            self,
            question: str,
            conversation_id: object,
            user_id: object,
            history: object = None,
            tools: object = None,
            system_prompt: object = None,
            reasoning_effort: object = None,
            images: object = None,
        ) -> AsyncIterator[dict[str, str]]:
            raise RuntimeError("provider failed")
            yield {"type": "delta", "content": "unreachable"}

    monkeypatch.setattr(
        "app.turns.pipeline.prepare.require_provider", _select_provider(FailingProvider())
    )

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hello",
            "conversation_id": str(conversation_id),
            "model_id": "claude-code-pty:anthropic/claude-opus-4-7",
        },
    )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "provider failed" in response.text
    assert "data: [DONE]" in response.text


@pytest.mark.anyio
async def test_chat_multi_turn_tool_call_flows_through_full_http_path(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """A realistic two-turn conversation (tool call then text) flows over HTTP.

    This test wires a real ``GeminiLLM`` with a ``ScriptedStreamFn`` through
    the full HTTP path:

        POST /api/v1/chat/
          → chat.py → GeminiLLM.stream() → run_model_tool_loop (real)
          → ScriptedStreamFn yields tool_call → echo_tool executes (real)
          → ScriptedStreamFn yields text reply
          → SSE frames: tool_use + tool_result + delta + [DONE]

    Only the LLM is replaced.  Every other component (HTTP routing,
    run_model_tool_loop, tool execution, SSE serialization) runs as in production.
    """
    from app.providers.gemini import GeminiLLM

    echo = echo_tool()
    script = ScriptedStreamFn(
        [
            tool_call_turn("echo", {"value": "test"}, turn_id="tc-http"),
            text_turn("I echoed test for you."),
        ]
    )

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(provider, "_stream_fn", script)

    # Inject both the provider and the echo tool into the chat path.
    monkeypatch.setattr("app.turns.pipeline.prepare.require_provider", _select_provider(provider))
    monkeypatch.setattr(
        "app.turns.pipeline.prepare.build_agent_tools", lambda *_args, **_kw: [echo]
    )

    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Tool HTTP Test"})

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "echo test",
            "conversation_id": str(conversation_id),
            "model_id": "claude-code-pty:anthropic/claude-opus-4-7",
        },
    )

    assert response.status_code == 200
    # All three event types must appear in the SSE body.
    assert '"type": "tool_use"' in response.text
    assert '"type": "tool_result"' in response.text
    assert '"type": "delta"' in response.text
    assert "data: [DONE]" in response.text

    # Both LLM turns were invoked (tool call + text reply).
    assert script.call_count == 2


@pytest.mark.anyio
async def test_chat_safety_layer_fires_and_surfaces_agent_terminated(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """The agent safety layer is wired into the real HTTP path end-to-end.

    This test exercises the full chain with a realistic runaway scenario:

        POST /api/v1/chat/
          → chat.py → GeminiLLM.stream()
          → safety_from_settings() builds AgentSafetyConfig(max_iterations=3)
          → ScriptedStreamFn serves 10 tool-call turns (runaway loop)
          → run_model_tool_loop terminates after exactly 3 iterations
          → AgentTerminatedEvent → StreamEvent(type="agent_terminated")
          → SSE frame with reason="max_iterations"

    ``safety_from_settings`` is patched to return ``max_iterations=3``.  The
    scripted stream has 10 turns, so the harness would keep looping forever
    without the safety cap.  The assertion that ``script.call_count == 3``
    confirms the safety fired, not just that an event appeared in the output.

    If the safety layer were disconnected, the loop would consume all 10
    turns and no ``agent_terminated`` frame would appear.
    """
    from app.providers.gemini import GeminiLLM

    # 10 tool-call turns — runaway loop the safety must stop.
    turns = [tool_call_turn("ping", {}, turn_id=f"tc-{i}") for i in range(10)]
    script = ScriptedStreamFn(turns)

    provider = GeminiLLM("gemini-test")
    monkeypatch.setattr(provider, "_stream_fn", script)

    # Limit to 3 iterations via the safety factory.
    monkeypatch.setattr(
        "app.providers.gemini.provider.safety_from_settings",
        lambda _settings: AgentSafetyConfig(
            max_iterations=3,
            max_wall_clock_seconds=None,
            max_consecutive_llm_errors=None,
            max_consecutive_tool_errors=None,
        ),
    )

    monkeypatch.setattr("app.turns.pipeline.prepare.require_provider", _select_provider(provider))
    monkeypatch.setattr(
        "app.turns.pipeline.prepare.build_agent_tools", lambda *_args, **_kw: [echo_tool("ping")]
    )

    conversation_id = uuid4()
    await client.post(f"/api/v1/conversations/{conversation_id}", json={"title": "Safety Test"})

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "go",
            "conversation_id": str(conversation_id),
            "model_id": "claude-code-pty:anthropic/claude-opus-4-7",
        },
    )

    assert response.status_code == 200
    # The SSE stream must contain an agent_terminated frame.
    assert '"type": "agent_terminated"' in response.text
    # The reason must be the iteration cap, not some other guard.
    assert "max_iterations" in response.text
    # The stream must still close cleanly.
    assert "data: [DONE]" in response.text
    # Safety fired at exactly 3 — not earlier, not later.
    assert script.call_count == 3
