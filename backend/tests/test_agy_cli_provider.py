"""Tests for the Antigravity agy CLI provider."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from app.providers.agy_api.provider import AgyApiLLM
from app.providers.agy_cli.command import AGY_BINARY_NAME, build_agy_command
from app.providers.agy_cli.logs import classify_log_line
from app.providers.agy_cli.output import (
    AGY_FINAL_CLOSE,
    AGY_FINAL_OPEN,
    build_framed_prompt,
    extract_final_answer,
    is_timeout_output,
)
from app.providers.agy_cli.provider import AgyCliLLM
from app.providers.agy_cli.session import parse_conversation_id
from app.providers.catalog import MODEL_CATALOG
from app.providers.factory import resolve_llm
from app.providers.model_id import Host, Vendor, parse_model_id


@pytest.mark.anyio
async def test_prepare_turn_session_clears_stale_cache_when_no_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    provider = AgyCliLLM("gemini-3.5-flash-high", workspace_root=None)
    provider._session_by_conversation[conversation_id] = "stale-session"

    async def fake_load_provider_session(_conversation_id: object) -> None:
        return None

    monkeypatch.setattr(
        "app.providers.agy_cli.provider.load_provider_session",
        fake_load_provider_session,
    )

    turn_state = await provider.prepare_turn_session(
        conversation_id=conversation_id,
        workspace_root=None,
        model_id=None,
        tools=None,
        reasoning_effort=None,
        question="hello",
    )

    assert turn_state.session_id is None
    assert conversation_id not in provider._session_by_conversation


def test_parse_model_id_accepts_agy_cli_host() -> None:
    parsed = parse_model_id("agy-cli:google/gemini-3.5-flash-high")

    assert parsed.host is Host.agy_cli
    assert parsed.vendor is Vendor.google
    assert parsed.model == "gemini-3.5-flash-high"
    assert parsed.id == "agy-cli:google/gemini-3.5-flash-high"


def test_parse_model_id_accepts_agy_api_host() -> None:
    parsed = parse_model_id("agy-api:anthropic/claude-sonnet-4-6")

    assert parsed.host is Host.agy_api
    assert parsed.vendor is Vendor.anthropic
    assert parsed.model == "claude-sonnet-4-6"
    assert parsed.id == "agy-api:anthropic/claude-sonnet-4-6"


def test_catalog_lists_agy_api_models() -> None:
    entries = [entry for entry in MODEL_CATALOG if entry.host is Host.agy_api]

    assert [entry.id for entry in entries] == [
        "agy-api:google/gemini-2.5-flash-thinking",
        "agy-api:google/gemini-3.5-flash-extra-low",
        "agy-api:google/gemini-3.5-flash-low",
        "agy-api:google/gemini-2.5-pro",
        "agy-api:google/gemini-3.1-pro-low",
        "agy-api:openai/gpt-oss-120b-medium",
        "agy-api:anthropic/claude-sonnet-4-6",
        "agy-api:anthropic/claude-opus-4-6-thinking",
        "agy-api:google/gemini-pro-agent",
        "agy-api:google/gemini-3-flash-agent",
        "agy-api:google/gemini-3.1-flash-image",
        "agy-api:google/gemini-3-flash",
        "agy-api:google/gemini-3.1-pro-high",
        "agy-api:google/gemini-2.5-flash",
        "agy-api:google/gemini-2.5-flash-lite",
        "agy-api:google/tab_jump_flash_lite_preview",
        "agy-api:google/tab_flash_lite_preview",
        "agy-api:google/gemini-3.1-flash-lite",
    ]


def test_catalog_omits_agy_cli_model_path() -> None:
    entries = [entry for entry in MODEL_CATALOG if entry.host is Host.agy_cli]

    assert entries == []


def test_build_agy_command_uses_absolute_workspace_and_log() -> None:
    command = build_agy_command(
        workspace_roots=[Path("/tmp/ws")],
        log_file=Path("/tmp/agy.log"),
        prompt="hello",
        timeout="10m",
        conversation_id="abc-123",
    )

    assert command == [
        AGY_BINARY_NAME,
        "--add-dir",
        "/tmp/ws",
        "--conversation",
        "abc-123",
        "--log-file",
        "/tmp/agy.log",
        "--print-timeout",
        "10m",
        "--print",
        "hello",
    ]


def test_extract_final_answer_returns_last_marker_block() -> None:
    stdout = (
        f"{AGY_FINAL_OPEN}old answer{AGY_FINAL_CLOSE}\n"
        "progress line\n"
        f"{AGY_FINAL_OPEN}new answer{AGY_FINAL_CLOSE}\n"
    )

    assert extract_final_answer(stdout) == "new answer"


def test_build_framed_prompt_wraps_history_and_question() -> None:
    prompt = build_framed_prompt(
        question="What next?",
        history=[{"role": "assistant", "content": "Prior answer"}],
        system_prompt="Be concise.",
    )

    assert "Be concise." in prompt
    assert "Assistant: Prior answer" in prompt
    assert "What next?" in prompt
    assert AGY_FINAL_OPEN in prompt
    assert AGY_FINAL_CLOSE in prompt
    assert "Answer directly without using tools" in prompt
    assert "You may use tools" not in prompt


def test_timeout_output_detection_matches_agy_print_timeout() -> None:
    assert is_timeout_output("Error: timed out waiting for response\n") is True
    assert is_timeout_output("normal response") is False


def test_parse_conversation_id_prefers_created_then_resumed() -> None:
    created = "I server.go:747] Created conversation 12345678-1234-4234-9234-123456789abc\n"
    resumed = (
        "I common.go:262] project: resuming conversation belonging to project ID: abc\n"
        "I printmode.go:125] Print mode: resuming conversation 99999999-9999-4999-9999-999999999999\n"
    )

    assert parse_conversation_id(created) == "12345678-1234-4234-9234-123456789abc"
    assert parse_conversation_id(resumed) == "99999999-9999-4999-9999-999999999999"


def test_classify_log_line_model_selection() -> None:
    event = classify_log_line(
        'I model_config_manager.go:157] Propagating selected model override to backend: label="Gemini 3.5 Flash (High)"'
    )

    assert event == {
        "event": "model_selected",
        "summary": "Gemini 3.5 Flash (High)",
    }


def test_classify_log_line_tool_confirmation() -> None:
    event = classify_log_line(
        'I tool_confirmation_manager.go:72] Auto-approving tool confirmation: "Edit" at step 6'
    )

    assert event == {
        "event": "tool_permission_auto_approved",
        "summary": "Edit",
    }


def test_factory_rejects_agy_cli_host_as_model_path() -> None:
    with pytest.raises(KeyError):
        resolve_llm("agy-cli:google/gemini-3.5-flash-high")


def test_factory_routes_agy_api_host_to_agy_api_llm() -> None:
    provider = resolve_llm("agy-api:google/gemini-3.5-flash-low")

    assert isinstance(provider, AgyApiLLM)
    assert provider._model_id == "gemini-3.5-flash-low"


class FakeProcess:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode
        self.pid = 123

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode


@pytest.mark.anyio
async def test_agy_provider_yields_last_framed_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "agy.log"

    async def fake_spawn(*_args: object, **_kwargs: object) -> FakeProcess:
        log_file.write_text(
            "I server.go:747] Created conversation 11111111-1111-4111-9111-111111111111\n"
        )
        return FakeProcess(
            b"<pawrrtal_final>old</pawrrtal_final>\n<pawrrtal_final>new</pawrrtal_final>\n"
        )

    monkeypatch.setattr("app.providers.agy_cli.provider.is_agy_cli_available", lambda: True)
    monkeypatch.setattr("app.providers.agy_cli.provider._make_log_file", lambda _cid: log_file)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    provider = AgyCliLLM("gemini-3.5-flash-high", workspace_root=None)
    events = [
        event
        async for event in provider.stream(
            "hello",
            conversation_id=uuid4(),
            user_id=uuid4(),
        )
    ]

    assert events == [
        {
            "type": "internal",
            "kind": "provider_session_created",
            "provider": "agy_cli",
            "session_id": "11111111-1111-4111-9111-111111111111",
        },
        {"type": "delta", "content": "new"},
    ]


@pytest.mark.anyio
async def test_agy_provider_surfaces_timeout_as_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "agy.log"

    async def fake_spawn(*_args: object, **_kwargs: object) -> FakeProcess:
        log_file.write_text("")
        return FakeProcess(b"Error: timed out waiting for response\n", returncode=0)

    monkeypatch.setattr("app.providers.agy_cli.provider.is_agy_cli_available", lambda: True)
    monkeypatch.setattr("app.providers.agy_cli.provider._make_log_file", lambda _cid: log_file)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    provider = AgyCliLLM("gemini-3.5-flash-high", workspace_root=tmp_path)
    events = [
        event
        async for event in provider.stream(
            "hello",
            conversation_id=uuid4(),
            user_id=uuid4(),
        )
    ]

    assert events == [
        {"type": "error", "content": "Antigravity CLI timed out waiting for a response."}
    ]


@pytest.mark.anyio
async def test_agy_provider_surfaces_unframed_stdout_as_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "agy.log"

    async def fake_spawn(*_args: object, **_kwargs: object) -> FakeProcess:
        log_file.write_text("")
        return FakeProcess(b"plain answer\n", returncode=0)

    monkeypatch.setattr("app.providers.agy_cli.provider.is_agy_cli_available", lambda: True)
    monkeypatch.setattr("app.providers.agy_cli.provider._make_log_file", lambda _cid: log_file)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    provider = AgyCliLLM("gemini-3.5-flash-high", workspace_root=tmp_path)
    events = [event async for event in provider.stream("hello", uuid4(), uuid4())]

    assert events == [
        {"type": "error", "content": "Antigravity CLI returned an unframed response."}
    ]
