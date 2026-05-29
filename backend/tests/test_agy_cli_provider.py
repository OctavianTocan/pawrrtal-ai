"""Tests for the Antigravity agy CLI provider."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

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


def test_parse_model_id_accepts_agy_cli_host() -> None:
    parsed = parse_model_id("agy-cli:google/gemini-3.5-flash-high")

    assert parsed.host is Host.agy_cli
    assert parsed.vendor is Vendor.google
    assert parsed.model == "gemini-3.5-flash-high"
    assert parsed.id == "agy-cli:google/gemini-3.5-flash-high"


def test_catalog_lists_agy_cli_model() -> None:
    entries = [entry for entry in MODEL_CATALOG if entry.host is Host.agy_cli]

    assert [entry.model for entry in entries] == ["gemini-3.5-flash-high"]
    assert entries[0].vendor is Vendor.google
    assert entries[0].display_name == "Gemini 3.5 Flash High (Antigravity)"
    assert entries[0].cost_per_mtok_in_usd == 0.0
    assert entries[0].cost_per_mtok_out_usd == 0.0


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


def test_timeout_output_detection_matches_agy_print_timeout() -> None:
    assert is_timeout_output("Error: timed out waiting for response\n") is True
    assert is_timeout_output("normal response") is False


def test_parse_conversation_id_prefers_created_then_resumed() -> None:
    created = "I server.go:747] Created conversation 1234-abcd\n"
    resumed = "I printmode.go:125] Print mode: resuming conversation 9999-zzzz\n"

    assert parse_conversation_id(created) == "1234-abcd"
    assert parse_conversation_id(resumed) == "9999-zzzz"


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


def test_factory_routes_agy_cli_host_to_agy_cli_llm() -> None:
    provider = resolve_llm("agy-cli:google/gemini-3.5-flash-high")

    assert isinstance(provider, AgyCliLLM)
    assert provider._model_id == "gemini-3.5-flash-high"


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
        log_file.write_text("I server.go:747] Created conversation conv-1\n")
        return FakeProcess(
            b"<pawrrtal_final>old</pawrrtal_final>\n<pawrrtal_final>new</pawrrtal_final>\n"
        )

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

    assert events == [{"type": "delta", "content": "new"}]


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
