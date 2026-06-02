"""Tests for the direct Antigravity API provider."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.agents.types import AgentTool
from app.providers.agy_api.auth import AgyApiAuth, AgyApiAuthError, load_agy_api_auth
from app.providers.agy_api.client import (
    _client,
    _event_from_sse_line,
    build_generate_body,
    close_agy_api_client,
)
from app.providers.agy_api.messages import build_agy_contents
from app.providers.agy_api.provider import AgyApiLLM, resolve_agy_api_wire_model_id
from app.providers.base import StreamEvent
from tests.agent_harness import ScriptedStreamFn, text_turn, thinking_then_text_turn, tool_call_turn


def test_load_agy_api_auth_uses_workspace_project_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    token_path = tmp_path / "token.json"
    projects_path = tmp_path / "projects.json"
    workspace = tmp_path / "workspace"
    token_path.write_text(
        json.dumps(
            {
                "token": {
                    "access_token": "access",
                    "expiry": "2999-01-01T00:00:00Z",
                }
            }
        )
    )
    projects_path.write_text(json.dumps({str(workspace): "project-1"}))
    monkeypatch.setattr("app.providers.agy_api.auth._TOKEN_PATH", token_path)
    monkeypatch.setattr("app.providers.agy_api.auth._PROJECTS_PATH", projects_path)

    auth = load_agy_api_auth(workspace)

    assert auth == AgyApiAuth(access_token="access", project_id="project-1")


def test_load_agy_api_auth_accepts_go_rfc3339_nano_expiry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    token_path = tmp_path / "token.json"
    projects_path = tmp_path / "projects.json"
    token_path.write_text(
        json.dumps(
            {
                "token": {
                    "access_token": "access",
                    "expiry": "2999-01-01T00:00:00.737057703Z",
                }
            }
        )
    )
    projects_path.write_text(json.dumps({"/workspace": "project-1"}))
    monkeypatch.setattr("app.providers.agy_api.auth._TOKEN_PATH", token_path)
    monkeypatch.setattr("app.providers.agy_api.auth._PROJECTS_PATH", projects_path)

    auth = load_agy_api_auth(Path("/workspace"))

    assert auth.project_id == "project-1"


def test_load_agy_api_auth_rejects_expired_access_token_without_rewriting_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    token_path = tmp_path / "token.json"
    projects_path = tmp_path / "projects.json"
    token_path.write_text(
        json.dumps(
            {
                "auth_method": "consumer",
                "token": {
                    "access_token": "expired-access",
                    "refresh_token": "refresh",
                    "token_type": "Bearer",
                    "expiry": "2000-01-01T00:00:00Z",
                },
            }
        )
    )
    projects_path.write_text(json.dumps({"/workspace": "project-1"}))
    monkeypatch.setattr("app.providers.agy_api.auth._TOKEN_PATH", token_path)
    monkeypatch.setattr("app.providers.agy_api.auth._PROJECTS_PATH", projects_path)

    with pytest.raises(AgyApiAuthError, match="run agy once"):
        load_agy_api_auth(Path("/workspace"))

    stored = json.loads(token_path.read_text())
    assert stored["auth_method"] == "consumer"
    assert stored["token"]["access_token"] == "expired-access"
    assert stored["token"]["refresh_token"] == "refresh"
    assert stored["token"]["expiry"] == "2000-01-01T00:00:00Z"


def test_build_generate_body_uses_gemini_style_history() -> None:
    body = build_generate_body(
        auth=AgyApiAuth(access_token="access", project_id="project-1"),
        model_id="gemini-3.5-flash",
        question="Now?",
        history=[
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ],
        system_prompt="Be concise.",
    )

    assert body["project"] == "project-1"
    assert body["model"] == "gemini-3.5-flash"
    assert body["request"]["contents"] == [
        {"role": "user", "parts": [{"text": "Hi"}]},
        {"role": "model", "parts": [{"text": "Hello"}]},
        {"role": "user", "parts": [{"text": "Now?"}]},
    ]
    assert body["request"]["systemInstruction"] == {
        "parts": [{"text": "Be concise."}],
    }


def test_build_generate_body_includes_tools_and_thinking_config() -> None:
    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        return ""

    tool = AgentTool(
        name="echo",
        description="Echo a value",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        execute=_execute,
    )

    body = build_generate_body(
        auth=AgyApiAuth(access_token="access", project_id="project-1"),
        model_id="gemini-3.1-flash-lite",
        question="Use a tool.",
        history=None,
        system_prompt=None,
        tools=[tool],
        generation_config={"thinkingConfig": {"includeThoughts": True, "thinkingLevel": "LOW"}},
    )

    request = body["request"]
    assert request["tools"] == [
        {
            "functionDeclarations": [
                {
                    "name": "echo",
                    "description": "Echo a value",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                    },
                }
            ]
        }
    ]
    assert request["generationConfig"] == {
        "thinkingConfig": {"includeThoughts": True, "thinkingLevel": "LOW"}
    }


def test_resolve_agy_api_wire_model_id_aliases_invalid_high_pro_key() -> None:
    assert resolve_agy_api_wire_model_id("gemini-3.1-pro-high") == "gemini-pro-agent"
    assert resolve_agy_api_wire_model_id("gemini-3.1-flash-lite") == "gemini-3.1-flash-lite"


def test_event_from_sse_line_extracts_text_delta() -> None:
    line = 'data: {"response":{"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}}'

    assert _event_from_sse_line(line) == {"type": "delta", "content": "hello"}


def test_event_from_sse_line_extracts_thinking_delta() -> None:
    line = (
        'data: {"response":{"candidates":[{"content":{"parts":'
        '[{"thought":true,"text":"reasoning"}]}}]}}'
    )

    assert _event_from_sse_line(line) == {
        "type": "thinking",
        "content": "reasoning",
        "block_index": 0,
    }


def test_event_from_sse_line_ignores_empty_thought_signature_chunk() -> None:
    line = (
        'data: {"response":{"candidates":[{"content":{"parts":'
        '[{"thoughtSignature":"abc","text":""}]}}]}}'
    )

    assert _event_from_sse_line(line) is None


def test_event_from_sse_line_extracts_function_call() -> None:
    line = (
        'data: {"response":{"candidates":[{"content":{"parts":'
        '[{"functionCall":{"name":"echo","args":{"value":"hi"},"id":"tc-0"}}]}}]}}'
    )

    assert _event_from_sse_line(line) == {
        "type": "tool_use",
        "name": "echo",
        "input": {"value": "hi"},
        "tool_use_id": "tc-0",
    }


def test_build_agy_contents_includes_function_response_id() -> None:
    contents = build_agy_contents(
        [
            {
                "role": "toolResult",
                "tool_call_id": "tc-0",
                "name": "echo",
                "content": [{"type": "text", "text": "tool-ok"}],
                "is_error": False,
            }
        ]
    )

    assert contents == [
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "echo",
                        "id": "tc-0",
                        "response": {"result": "tool-ok"},
                    }
                }
            ],
        }
    ]


@pytest.mark.anyio
async def test_agy_api_client_reuses_warm_http_client() -> None:
    await close_agy_api_client()

    first = _client()
    second = _client()

    assert first is second
    await close_agy_api_client()
    assert first.is_closed

    replacement = _client()
    try:
        assert replacement is not first
        assert not replacement.is_closed
    finally:
        await close_agy_api_client()


@pytest.mark.anyio
async def test_agy_api_provider_surfaces_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.providers.agy_api.provider.load_agy_api_auth",
        lambda _workspace_root: (_ for _ in ()).throw(AgyApiAuthError("no token")),
    )
    provider = AgyApiLLM("gemini-3.5-flash", workspace_root=None)

    events = [
        event
        async for event in provider.stream(
            "hello",
            conversation_id=uuid4(),
            user_id=uuid4(),
        )
    ]

    assert events == [{"type": "error", "content": "Antigravity API auth unavailable: no token"}]


@pytest.mark.anyio
async def test_agy_api_provider_emits_thinking_from_agent_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AgyApiLLM("gemini-test", workspace_root=None)
    script = ScriptedStreamFn([thinking_then_text_turn("reasoning", "answer")])
    monkeypatch.setattr(provider, "_stream_fn", script)

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            "hello",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
        )
    ]

    assert any(e["type"] == "thinking" and e.get("content") == "reasoning" for e in events)
    assert any(e["type"] == "delta" and e.get("content") == "answer" for e in events)


@pytest.mark.anyio
async def test_agy_api_provider_dispatches_tool_calls_through_real_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AgyApiLLM("gemini-test", workspace_root=None)
    executed: list[str] = []

    async def echo_execute(tool_call_id: str, **kwargs: object) -> str:
        executed.append(str(kwargs.get("value", "")))
        return f"echoed: {kwargs.get('value', '')}"

    echo = AgentTool(
        name="echo",
        description="Echo",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        execute=echo_execute,
    )
    script = ScriptedStreamFn(
        [
            tool_call_turn("echo", {"value": "hi"}, turn_id="tc-0"),
            text_turn("done"),
        ]
    )
    monkeypatch.setattr(provider, "_stream_fn", script)

    events: list[StreamEvent] = [
        event
        async for event in provider.stream(
            "echo hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            history=[],
            tools=[echo],
        )
    ]

    assert executed == ["hi"]
    assert script.call_count == 2
    assert any(e["type"] == "tool_use" for e in events)
    assert any(e["type"] == "tool_result" for e in events)
    assert any(e["type"] == "delta" and e.get("content") == "done" for e in events)
