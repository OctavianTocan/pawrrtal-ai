"""Tests for the Gemini CLI provider and its ACP client bridge.

The provider drives a subprocess (``gemini --acp``) so end-to-end
tests require the binary on PATH. These tests focus on the
deterministic pieces that don't:

* Catalog membership, factory dispatch, and the availability probe.
* :func:`render_history_prefix` truncation contract.
* :class:`PawrrtalAcpClient`'s session-update translation,
  permission handling, filesystem callbacks, and terminal stubs.
* :func:`ensure_workspace_path` symlink-traversal rejection.
* :func:`run_prompt_and_drain`'s queue sentinel behavior.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from acp import RequestError
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AvailableCommandsUpdate,
    ConfigOptionUpdate,
    Cost,
    CurrentModeUpdate,
    EmbeddedResourceContentBlock,
    FileEditToolCallContent,
    ImageContentBlock,
    PermissionOption,
    ResourceContentBlock,
    SessionInfoUpdate,
    TerminalToolCallContent,
    TextContentBlock,
    TextResourceContents,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
    UserMessageChunk,
)

from app.core.providers.base import StreamEvent
from app.core.providers.catalog import MODEL_CATALOG
from app.core.providers.factory import resolve_llm
from app.core.providers.gemini_cli import (
    GeminiCliLLM,
    is_gemini_cli_available,
    render_history_prefix,
)
from app.core.providers.gemini_cli.acp import AcpFatalError, _drain_queue, open_session
from app.core.providers.gemini_cli.client import (
    PawrrtalAcpClient,
    _stream_event_for_update,
    _tool_progress_event,
    _usage_event,
    pick_allow_option,
    text_from_content_block,
    text_from_tool_content_item,
)
from app.core.providers.gemini_cli.fs import ensure_workspace_path, slice_text
from app.core.providers.gemini_cli.provider import _spawn_subprocess
from app.core.providers.model_id import Host, Vendor

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


GEMINI_CLI_MODELS = (
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-pro-preview",
    "gemini-3.1-pro-preview",
)


def test_catalog_lists_all_five_gemini_cli_models() -> None:
    cli_entries = [e for e in MODEL_CATALOG if e.host is Host.gemini_cli]
    assert {e.model for e in cli_entries} == set(GEMINI_CLI_MODELS)
    for entry in cli_entries:
        assert entry.vendor is Vendor.google
        # CLI uses local Google account auth — not API-billed via us.
        assert entry.cost_per_mtok_in_usd == 0.0
        assert entry.cost_per_mtok_out_usd == 0.0


def test_catalog_ids_use_gemini_cli_host_prefix() -> None:
    cli_entries = [e for e in MODEL_CATALOG if e.host is Host.gemini_cli]
    for entry in cli_entries:
        assert entry.id == f"gemini-cli:google/{entry.model}"


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", GEMINI_CLI_MODELS)
def test_factory_routes_gemini_cli_host_to_gemini_cli_llm(model: str) -> None:
    provider = resolve_llm(f"gemini-cli:google/{model}")
    assert isinstance(provider, GeminiCliLLM)


def test_factory_keeps_google_ai_host_on_native_provider() -> None:
    # Sanity check — adding gemini-cli must not steal the canonical
    # google-ai routing from the native SDK provider.
    from app.core.providers.gemini_provider import GeminiLLM

    native = resolve_llm("google-ai:google/gemini-3-flash-preview")
    assert isinstance(native, GeminiLLM)
    assert not isinstance(native, GeminiCliLLM)


def test_factory_host_table_is_exhaustive() -> None:
    # Catches the case where someone adds a new ``Host`` member without
    # wiring it into ``HOST_TO_PROVIDER`` — the module-level assertion
    # in factory.py would have raised at import time, so this is a
    # belt-and-braces check that every member has a class.
    from app.core.providers.factory import HOST_TO_PROVIDER

    assert set(HOST_TO_PROVIDER) == set(Host)


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------


def test_is_gemini_cli_available_when_binary_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.providers.gemini_cli.provider.shutil.which",
        lambda _name: "/usr/local/bin/gemini",
    )
    assert is_gemini_cli_available() is True


def test_is_gemini_cli_available_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.providers.gemini_cli.provider.shutil.which",
        lambda _name: None,
    )
    assert is_gemini_cli_available() is False


# ---------------------------------------------------------------------------
# History prefix rendering
# ---------------------------------------------------------------------------


def test_render_history_prefix_empty_when_no_history_and_no_system_prompt() -> None:
    assert render_history_prefix(history=None, system_prompt=None) == ""
    assert render_history_prefix(history=[], system_prompt="") == ""


def test_render_history_prefix_wraps_system_prompt() -> None:
    out = render_history_prefix(history=None, system_prompt="you are helpful")
    assert "--- BEGIN SYSTEM CONTEXT ---" in out
    assert "you are helpful" in out
    assert "--- END SYSTEM CONTEXT ---" in out


def test_render_history_prefix_wraps_conversation_history() -> None:
    history = [
        {"role": "user", "content": "what's 2+2?"},
        {"role": "assistant", "content": "4"},
    ]
    out = render_history_prefix(history=history, system_prompt=None)
    assert "--- BEGIN PRIOR CONVERSATION ---" in out
    assert "User: what's 2+2?" in out
    assert "Assistant: 4" in out
    assert "--- END PRIOR CONVERSATION ---" in out


def test_render_history_prefix_skips_blank_rows() -> None:
    history = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "   "},
        {"role": "user", "content": "real question"},
    ]
    out = render_history_prefix(history=history, system_prompt=None)
    assert "User: real question" in out
    assert out.count("User:") == 1
    assert "Assistant:" not in out


def test_render_history_prefix_truncates_inner_content_keeping_markers() -> None:
    # Truncation must operate on the inner content, not the wrapped
    # body — otherwise a long history drops the BEGIN markers and
    # leaves an unbalanced END.
    history = [{"role": "user", "content": f"row {i}: " + "x" * 800} for i in range(200)]
    out = render_history_prefix(history=history, system_prompt=None)
    assert "--- BEGIN PRIOR CONVERSATION ---" in out
    assert "--- END PRIOR CONVERSATION ---" in out
    # Tail preserved — most-recent rows survive.
    assert "row 199:" in out
    # Head dropped after the cap.
    assert "row 0:" not in out
    # Inner content capped; the wrappers add a small bounded overhead.
    assert len(out) < 13_000


def test_render_history_prefix_caps_to_last_twenty_history_rows() -> None:
    history = [{"role": "user", "content": f"row {i}"} for i in range(50)]
    out = render_history_prefix(history=history, system_prompt=None)
    assert "row 49" in out
    assert "row 30" in out
    assert "row 29" not in out  # 20-row window


def test_render_history_prefix_truncates_oversized_system_prompt() -> None:
    huge_prompt = "you are helpful: " + ("x" * 50_000)
    out = render_history_prefix(history=None, system_prompt=huge_prompt)
    assert out.startswith("--- BEGIN SYSTEM CONTEXT ---")
    assert "--- END SYSTEM CONTEXT ---" in out
    assert len(out) < 13_000


# ---------------------------------------------------------------------------
# pick_allow_option
# ---------------------------------------------------------------------------


def test_pick_allow_option_prefers_allow_once() -> None:
    options = [
        PermissionOption(option_id="0", name="Always", kind="allow_always"),
        PermissionOption(option_id="1", name="Once", kind="allow_once"),
        PermissionOption(option_id="2", name="No", kind="reject_once"),
    ]
    chosen = pick_allow_option(options)
    assert chosen is not None
    assert chosen.kind == "allow_once"


def test_pick_allow_option_returns_none_when_no_allow_kind() -> None:
    options = [
        PermissionOption(option_id="0", name="No", kind="reject_once"),
        PermissionOption(option_id="1", name="Never", kind="reject_always"),
    ]
    assert pick_allow_option(options) is None


# ---------------------------------------------------------------------------
# text_from_content_block / text_from_tool_content_item
# ---------------------------------------------------------------------------


def test_text_from_content_block_pulls_text_payload() -> None:
    block = TextContentBlock(type="text", text="hello world")
    assert text_from_content_block(block) == "hello world"


def test_text_from_content_block_returns_empty_for_image_blocks() -> None:
    block = ImageContentBlock(type="image", data="<base64>", mime_type="image/png")
    assert text_from_content_block(block) == ""


def test_text_from_content_block_resource_link_falls_back_to_name() -> None:
    block = ResourceContentBlock(
        type="resource_link",
        name="readme",
        uri="file:///x/readme.md",
    )
    assert text_from_content_block(block) == "readme"


def test_text_from_content_block_embedded_text_resource() -> None:
    block = EmbeddedResourceContentBlock(
        type="resource",
        resource=TextResourceContents(uri="file:///x.py", text="print('ok')"),
    )
    assert text_from_content_block(block) == "print('ok')"


def test_text_from_content_block_unknown_type_returns_empty() -> None:
    class Other:
        pass

    assert text_from_content_block(Other()) == ""


def test_text_from_tool_content_item_file_edit() -> None:
    item = FileEditToolCallContent(type="diff", path="/x", old_text=None, new_text="y")
    assert text_from_tool_content_item(item) == "diff: /x"


def test_text_from_tool_content_item_terminal_ref() -> None:
    item = TerminalToolCallContent(type="terminal", terminal_id="t-1")
    assert text_from_tool_content_item(item) == "terminal: t-1"


# ---------------------------------------------------------------------------
# _stream_event_for_update — the translation surface
# ---------------------------------------------------------------------------


def test_stream_event_for_update_agent_message_chunk_becomes_delta() -> None:
    update = AgentMessageChunk(
        session_update="agent_message_chunk",
        content=TextContentBlock(type="text", text="hello"),
    )
    event = _stream_event_for_update(update)
    assert event == {"type": "delta", "content": "hello"}


def test_stream_event_for_update_agent_message_chunk_empty_text_returns_none() -> None:
    update = AgentMessageChunk(
        session_update="agent_message_chunk",
        content=TextContentBlock(type="text", text=""),
    )
    assert _stream_event_for_update(update) is None


def test_stream_event_for_update_agent_thought_chunk_becomes_thinking() -> None:
    update = AgentThoughtChunk(
        session_update="agent_thought_chunk",
        content=TextContentBlock(type="text", text="hmm"),
    )
    event = _stream_event_for_update(update)
    assert event == {"type": "thinking", "content": "hmm"}


def test_stream_event_for_update_tool_call_start_carries_id_and_kind() -> None:
    update = ToolCallStart(
        session_update="tool_call",
        tool_call_id="tc_1",
        title="Reading file",
        kind="read",
        raw_input={"path": "x.txt"},
    )
    event = _stream_event_for_update(update)
    assert event is not None
    assert event["type"] == "tool_use"
    assert event["tool_use_id"] == "tc_1"
    assert event["name"] == "read"  # kind preferred over title
    assert event["input"] == {"path": "x.txt"}


def test_stream_event_for_update_tool_progress_in_progress_dropped() -> None:
    update = ToolCallProgress(
        session_update="tool_call_update",
        tool_call_id="tc_1",
        status="in_progress",
    )
    assert _stream_event_for_update(update) is None


def test_stream_event_for_update_tool_progress_completed_emits_tool_result() -> None:
    update = ToolCallProgress(
        session_update="tool_call_update",
        tool_call_id="tc_1",
        status="completed",
        content=[FileEditToolCallContent(type="diff", path="/x", old_text=None, new_text="y")],
    )
    event = _stream_event_for_update(update)
    assert event == {"type": "tool_result", "tool_use_id": "tc_1", "content": "diff: /x"}


def test_tool_progress_failed_with_no_content_substitutes_placeholder() -> None:
    update = ToolCallProgress(
        session_update="tool_call_update",
        tool_call_id="tc_1",
        status="failed",
    )
    event = _tool_progress_event(update)
    assert event is not None
    assert event["type"] == "tool_result"
    assert event["content"] == "<tool failed>"


def test_tool_progress_joins_multiple_content_items() -> None:
    update = ToolCallProgress(
        session_update="tool_call_update",
        tool_call_id="tc",
        status="completed",
        content=[
            FileEditToolCallContent(type="diff", path="/a", old_text=None, new_text="x"),
            FileEditToolCallContent(type="diff", path="/b", old_text="y", new_text="z"),
        ],
    )
    event = _tool_progress_event(update)
    assert event is not None
    assert event["content"] == "diff: /a\ndiff: /b"


def test_stream_event_for_update_usage_with_cost_emits_usage_event() -> None:
    update = UsageUpdate(
        session_update="usage_update",
        size=1000,
        used=100,
        cost=Cost(amount=0.0042, currency="USD"),
    )
    event = _stream_event_for_update(update)
    assert event is not None
    assert event["type"] == "usage"
    assert event["cost_usd"] == pytest.approx(0.0042)


def test_usage_event_without_cost_returns_none() -> None:
    update = UsageUpdate(session_update="usage_update", size=1000, used=100)
    assert _usage_event(update) is None


@pytest.mark.parametrize(
    "update",
    [
        AgentPlanUpdate(session_update="plan", entries=[]),
        AvailableCommandsUpdate(session_update="available_commands_update", available_commands=[]),
        CurrentModeUpdate(session_update="current_mode_update", current_mode_id="default"),
        ConfigOptionUpdate(session_update="config_option_update", config_options=[]),
        SessionInfoUpdate(session_update="session_info_update"),
        UserMessageChunk(
            session_update="user_message_chunk",
            content=TextContentBlock(type="text", text="echoed"),
        ),
    ],
)
def test_stream_event_for_update_drops_editor_ui_hints(update: Any) -> None:
    assert _stream_event_for_update(update) is None


def test_stream_event_for_update_unknown_variant_returns_none() -> None:
    # Forward-compat: an ACP-SDK version that introduces a new update
    # type must not crash the translation layer.
    class FutureUpdate:
        pass

    assert _stream_event_for_update(FutureUpdate()) is None


# ---------------------------------------------------------------------------
# PawrrtalAcpClient.session_update — the queue side
# ---------------------------------------------------------------------------


def _make_client(
    *,
    workspace_root: Path | None = None,
    permission_check: Any = None,
) -> tuple[PawrrtalAcpClient, asyncio.Queue[StreamEvent | None]]:
    queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
    client = PawrrtalAcpClient(
        event_queue=queue,
        workspace_root=workspace_root,
        permission_check=permission_check,
    )
    return client, queue


@pytest.mark.anyio
async def test_session_update_pushes_delta_onto_queue() -> None:
    client, queue = _make_client()
    update = AgentMessageChunk(
        session_update="agent_message_chunk",
        content=TextContentBlock(type="text", text="hi"),
    )
    await client.session_update(session_id="s1", update=update)
    assert queue.get_nowait() == {"type": "delta", "content": "hi"}


@pytest.mark.anyio
async def test_session_update_drops_empty_chunks() -> None:
    client, queue = _make_client()
    update = AgentMessageChunk(
        session_update="agent_message_chunk",
        content=TextContentBlock(type="text", text=""),
    )
    await client.session_update(session_id="s1", update=update)
    assert queue.empty()


# ---------------------------------------------------------------------------
# PawrrtalAcpClient.request_permission
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_request_permission_auto_approves_allow_once_when_no_closure() -> None:
    client, queue = _make_client()
    options = [PermissionOption(option_id="1", name="Once", kind="allow_once")]
    tool_call = ToolCallUpdate(tool_call_id="tc", title="Bash", raw_input={"cmd": "ls"})
    resp = await client.request_permission(options=options, session_id="s1", tool_call=tool_call)
    assert resp.outcome.option_id == "1"  # type: ignore[attr-defined]
    assert queue.empty()  # no error event when auto-approving


@pytest.mark.anyio
async def test_request_permission_pushes_error_event_on_denial() -> None:
    async def deny(_name: str, _args: dict[str, Any]) -> dict[str, Any]:
        return {"allow": False, "reason": "blocked by policy", "violation_type": "tool_blocked"}

    client, queue = _make_client(permission_check=deny)
    options = [PermissionOption(option_id="1", name="Once", kind="allow_once")]
    tool_call = ToolCallUpdate(tool_call_id="tc", title="Bash", raw_input={"cmd": "rm -rf"})
    resp = await client.request_permission(options=options, session_id="s1", tool_call=tool_call)
    assert resp.outcome.outcome == "cancelled"  # type: ignore[attr-defined]
    event = queue.get_nowait()
    assert event["type"] == "error"
    assert "Bash" in event["content"]
    assert "blocked by policy" in event["content"]


@pytest.mark.anyio
async def test_request_permission_pushes_error_event_when_no_allow_offered() -> None:
    client, queue = _make_client()
    options = [PermissionOption(option_id="0", name="No", kind="reject_once")]
    tool_call = ToolCallUpdate(tool_call_id="tc", title="Bash", raw_input={})
    resp = await client.request_permission(options=options, session_id="s1", tool_call=tool_call)
    assert resp.outcome.outcome == "cancelled"  # type: ignore[attr-defined]
    event = queue.get_nowait()
    assert event["type"] == "error"


@pytest.mark.anyio
async def test_request_permission_forwards_tool_name_and_arguments_to_closure() -> None:
    captured: list[tuple[str, dict[str, Any]]] = []

    async def allow(name: str, args: dict[str, Any]) -> dict[str, Any]:
        captured.append((name, args))
        return {"allow": True, "reason": None, "violation_type": None}

    client, _queue = _make_client(permission_check=allow)
    options = [PermissionOption(option_id="1", name="Once", kind="allow_once")]
    tool_call = ToolCallUpdate(tool_call_id="tc", title="Bash", raw_input={"cmd": "ls"})
    await client.request_permission(options=options, session_id="s1", tool_call=tool_call)
    assert captured == [("Bash", {"cmd": "ls"})]


# ---------------------------------------------------------------------------
# PawrrtalAcpClient.read_text_file / write_text_file
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_text_file_returns_full_contents(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    target.write_text("alpha\nbravo\ncharlie\n")
    client, _queue = _make_client(workspace_root=tmp_path)
    resp = await client.read_text_file(path=str(target), session_id="s1")
    assert resp.content == "alpha\nbravo\ncharlie\n"


@pytest.mark.anyio
async def test_read_text_file_slices_by_line_and_limit(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("a\nb\nc\nd\ne\n")
    client, _queue = _make_client(workspace_root=tmp_path)
    resp = await client.read_text_file(path=str(target), session_id="s1", line=2, limit=2)
    assert resp.content == "b\nc"


@pytest.mark.anyio
async def test_read_text_file_rejects_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    client, _queue = _make_client(workspace_root=workspace)
    with pytest.raises(RequestError):
        await client.read_text_file(path=str(outside), session_id="s1")


@pytest.mark.anyio
async def test_read_text_file_missing_file_raises_request_error(tmp_path: Path) -> None:
    client, _queue = _make_client(workspace_root=tmp_path)
    with pytest.raises(RequestError):
        await client.read_text_file(path=str(tmp_path / "missing.txt"), session_id="s1")


@pytest.mark.anyio
async def test_write_text_file_creates_intermediate_directories(tmp_path: Path) -> None:
    client, _queue = _make_client(workspace_root=tmp_path)
    nested = tmp_path / "deep" / "nested" / "out.txt"
    await client.write_text_file(content="hello", path=str(nested), session_id="s1")
    assert nested.read_text() == "hello"


@pytest.mark.anyio
async def test_write_text_file_rejects_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    client, _queue = _make_client(workspace_root=workspace)
    with pytest.raises(RequestError):
        await client.write_text_file(content="nope", path=str(outside), session_id="s1")


# ---------------------------------------------------------------------------
# Workspace path validation (including symlink traversal)
# ---------------------------------------------------------------------------


def test_ensure_workspace_path_accepts_inside_workspace(tmp_path: Path) -> None:
    target = tmp_path / "subdir" / "file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hi")
    resolved = ensure_workspace_path(str(target), tmp_path)
    assert resolved == target.resolve()


def test_ensure_workspace_path_rejects_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sibling = tmp_path / "outside" / "secret.txt"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("don't read me")
    with pytest.raises(RequestError):
        ensure_workspace_path(str(sibling), workspace)


def test_ensure_workspace_path_rejects_relative_path(tmp_path: Path) -> None:
    with pytest.raises(RequestError):
        ensure_workspace_path("./relative.txt", tmp_path)


def test_ensure_workspace_path_rejects_when_workspace_root_missing(tmp_path: Path) -> None:
    with pytest.raises(RequestError):
        ensure_workspace_path(str(tmp_path / "file.txt"), None)


def test_ensure_workspace_path_rejects_symlink_pointing_outside(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("don't read me")
    sneak = workspace / "sneak.txt"
    sneak.symlink_to(secret)
    with pytest.raises(RequestError):
        ensure_workspace_path(str(sneak), workspace)


def test_ensure_workspace_path_follows_symlink_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real = workspace / "real.txt"
    real.write_text("ok")
    link = workspace / "link.txt"
    link.symlink_to(real)
    resolved = ensure_workspace_path(str(link), workspace)
    assert resolved == real.resolve()


# ---------------------------------------------------------------------------
# slice_text edge cases
# ---------------------------------------------------------------------------


def test_slice_text_full_when_no_line_or_limit() -> None:
    assert slice_text("a\nb\nc", None, None) == "a\nb\nc"


def test_slice_text_handles_line_beyond_end() -> None:
    assert slice_text("a\nb", line=10, limit=5) == ""


def test_slice_text_clamps_negative_line_to_start() -> None:
    assert slice_text("a\nb\nc", line=-1, limit=2) == "a\nb"


# ---------------------------------------------------------------------------
# Terminal methods + ext methods raise method_not_found
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.create_terminal(command="ls", session_id="s1"),
        lambda c: c.terminal_output(session_id="s1", terminal_id="t1"),
        lambda c: c.release_terminal(session_id="s1", terminal_id="t1"),
        lambda c: c.wait_for_terminal_exit(session_id="s1", terminal_id="t1"),
        lambda c: c.kill_terminal(session_id="s1", terminal_id="t1"),
        lambda c: c.ext_method("custom", {}),
    ],
    ids=["create", "output", "release", "wait", "kill", "ext_method"],
)
async def test_unsupported_methods_raise_method_not_found(call: Any) -> None:
    client, _queue = _make_client()
    with pytest.raises(RequestError):
        await call(client)


# ---------------------------------------------------------------------------
# Queue drain sentinel
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_drain_queue_yields_until_none_sentinel() -> None:
    queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
    await queue.put(StreamEvent(type="delta", content="a"))
    await queue.put(StreamEvent(type="delta", content="b"))
    await queue.put(None)
    # Anything queued after the sentinel must not surface — the sentinel
    # is the only signal the drainer trusts.
    await queue.put(StreamEvent(type="delta", content="after"))
    yielded = [event async for event in _drain_queue(queue)]
    assert yielded == [
        {"type": "delta", "content": "a"},
        {"type": "delta", "content": "b"},
    ]


# ---------------------------------------------------------------------------
# ACP cwd handling
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_spawn_subprocess_resolves_relative_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspaces" / "dev-admin"
    workspace.mkdir(parents=True)
    captured: dict[str, Any] = {}

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> object:
        captured["args"] = args
        captured["cwd"] = kwargs["cwd"]
        return object()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.core.providers.gemini_cli.provider.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    proc = await _spawn_subprocess("gemini-2.5-flash", Path("workspaces/dev-admin"))

    assert proc is not None
    assert captured["cwd"] == str(workspace.resolve())


@pytest.mark.anyio
async def test_open_session_sends_absolute_cwd_for_relative_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspaces" / "dev-admin"
    workspace.mkdir(parents=True)

    class FakeConn:
        async def initialize(self, **_kwargs: Any) -> object:
            return object()

        async def new_session(self, *, cwd: str, mcp_servers: list[Any]) -> object:
            assert cwd == str(workspace.resolve())
            assert mcp_servers == []
            return type("Session", (), {"session_id": "session-1"})()

    monkeypatch.chdir(tmp_path)

    assert await open_session(FakeConn(), Path("workspaces/dev-admin")) == "session-1"


@pytest.mark.anyio
async def test_open_session_surfaces_structured_request_error_detail() -> None:
    class FakeConn:
        async def initialize(self, **_kwargs: Any) -> object:
            return object()

        async def new_session(self, **_kwargs: Any) -> object:
            raise RequestError(
                -32603,
                "Internal error",
                {"details": "Directory does not exist: x/y"},
            )

    with pytest.raises(AcpFatalError, match="Directory does not exist: x/y"):
        await open_session(FakeConn(), Path("workspaces/dev-admin"))


# ---------------------------------------------------------------------------
# GeminiCliLLM.stream() — error paths reachable without the binary
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stream_yields_error_event_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.core.providers.gemini_cli.provider.shutil.which",
        lambda _name: None,
    )
    provider = GeminiCliLLM("gemini-2.5-pro", workspace_root=tmp_path)
    events = [
        event
        async for event in provider.stream(
            question="hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
        )
    ]
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "Gemini CLI binary not found" in events[0]["content"]


@pytest.mark.anyio
async def test_stream_yields_error_event_when_spawn_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.core.providers.gemini_cli.provider.shutil.which",
        lambda _name: "/usr/local/bin/gemini",
    )

    async def fake_spawn(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "app.core.providers.gemini_cli.provider._spawn_subprocess",
        fake_spawn,
    )
    provider = GeminiCliLLM("gemini-2.5-pro", workspace_root=tmp_path)
    events = [
        event
        async for event in provider.stream(
            question="hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
        )
    ]
    assert events == [{"type": "error", "content": "Failed to spawn Gemini CLI subprocess."}]


@pytest.mark.anyio
async def test_stream_drops_images_tools_and_reasoning_for_protocol_parity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Pin the AILLM-protocol-parity contract: a non-empty tools/images
    # list does not raise — the provider logs and ignores. The binary
    # is missing so the stream terminates with a single error event.
    monkeypatch.setattr(
        "app.core.providers.gemini_cli.provider.shutil.which",
        lambda _name: None,
    )
    provider = GeminiCliLLM("gemini-2.5-pro", workspace_root=tmp_path)
    events = [
        event
        async for event in provider.stream(
            question="hi",
            conversation_id=uuid4(),
            user_id=uuid4(),
            tools=[],  # empty list is fine — empty/None equivalent
            images=[{"data": "<b64>", "media_type": "image/png"}],
            reasoning_effort="high",
        )
    ]
    assert len(events) == 1
    assert events[0]["type"] == "error"
