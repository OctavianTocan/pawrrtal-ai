"""Tests for the Claude Agent SDK provider.

The Claude SDK runs the Claude Code CLI as a subprocess. We do not exercise
that subprocess in unit tests — instead, we mock :func:`claude_agent_sdk.query`
(re-exported into ``app.core.providers.claude_provider`` as ``query``) and
assert that:

- :class:`ClaudeLLM` builds correct :class:`ClaudeAgentOptions`
- it translates every Claude SDK message/block type into a ``StreamEvent``
- it converts every documented SDK error into a stream-level error event
- it reuses the ``conversation_id`` as the SDK session ID and switches
  from ``session_id`` (first turn) to ``resume`` (subsequent turns)
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ProcessError,
    RateLimitEvent,
    RateLimitInfo,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from app.core.providers import (
    ClaudeLLM,
    ClaudeLLMConfig,
    StreamEvent,
)
from app.core.providers import claude_provider as cp_module
from app.core.providers.claude_provider import (
    _events_from_message,
    _resolve_sdk_model,
    _tool_result_to_text,
)

# Note: ClaudeLLM runs its own agent loop via the Claude Code SDK subprocess
# (max_turns controls iteration depth).  It does NOT use the Python agent_loop
# or ScriptedStreamFn — those apply to GeminiLLM and the generic loop seam.
# Scenario-level tests here exercise the full provider.stream() path using a
# mock SDK ``query`` that returns realistic SDK message sequences.

# ---------------------------------------------------------------------------
# Test plumbing
# ---------------------------------------------------------------------------


@pytest.fixture
def conversation_id() -> UUID:
    """A fresh conversation UUID for each test."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """A fresh user UUID for each test."""
    return uuid4()


@pytest.fixture
def force_new_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make :func:`get_session_info` claim the session does not exist.

    ``ClaudeLLM`` uses this probe to choose between ``session_id``
    (first turn) and ``resume`` (subsequent turns). Forcing the answer
    keeps tests deterministic without touching the local Claude
    transcript directory.
    """
    monkeypatch.setattr(cp_module, "_session_exists", lambda *_a, **_k: False)


@pytest.fixture
def force_resume_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make :func:`get_session_info` claim the session already exists."""
    monkeypatch.setattr(cp_module, "_session_exists", lambda *_a, **_k: True)


def _patch_query(
    monkeypatch: pytest.MonkeyPatch,
    fake: Callable[..., AsyncIterator[Any]],
) -> list[ClaudeAgentOptions]:
    """Replace ``claude_provider.query`` with ``fake`` and capture the options used.

    Returns:
        A list that the recorder appends to. Use it to assert on the
        :class:`ClaudeAgentOptions` that ``ClaudeLLM`` built.
    """
    captured: list[ClaudeAgentOptions] = []

    def _wrapper(
        *,
        prompt: str,
        options: ClaudeAgentOptions,
        transport: Any | None = None,
    ) -> AsyncIterator[Any]:
        captured.append(options)
        return fake(prompt=prompt, options=options, transport=transport)

    monkeypatch.setattr(cp_module, "query", _wrapper)
    return captured


def _async_iter(messages: list[Any]) -> Callable[..., AsyncIterator[Any]]:
    """Return a fake ``query`` that yields the given messages and stops."""

    async def _gen(**_: Any) -> AsyncIterator[Any]:
        for message in messages:
            yield message

    return _gen


def _async_raises(error: BaseException) -> Callable[..., AsyncIterator[Any]]:
    """Return a fake ``query`` that raises ``error`` on the first iteration."""

    async def _gen(**_: Any) -> AsyncIterator[Any]:
        raise error
        yield  # pragma: no cover — keeps mypy/pyright happy about return type

    return _gen


async def _collect(
    provider: ClaudeLLM,
    question: str,
    conversation_id: UUID,
    user_id: UUID,
    **stream_kwargs: Any,
) -> list[StreamEvent]:
    return [
        event
        async for event in provider.stream(question, conversation_id, user_id, **stream_kwargs)
    ]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestResolveSdkModel:
    """:func:`_resolve_sdk_model` should map known IDs and pass through unknowns."""

    @pytest.mark.parametrize(
        "model_id",
        [
            "claude-haiku-4-5",
            "claude-sonnet-4-5",
            "claude-sonnet-4-6",
            "claude-opus-4-5",
            "claude-opus-4-6",
            "claude-opus-4-7",
        ],
    )
    def test_known_models_map_to_themselves(self, model_id: str) -> None:
        """Known Claude model IDs should resolve to a non-empty SDK model string."""
        assert _resolve_sdk_model(model_id) == model_id

    def test_unknown_model_passes_through(self) -> None:
        """Unknown IDs fall through unchanged so new model IDs work without a code change."""
        assert _resolve_sdk_model("claude-future-9-9") == "claude-future-9-9"


class TestToolResultToText:
    """:func:`_tool_result_to_text` should normalise every shape into a string."""

    def test_none_becomes_empty_string(self) -> None:
        """None content should serialize as the empty string."""
        assert _tool_result_to_text(None) == ""

    def test_string_passes_through(self) -> None:
        """Plain string content should pass through verbatim."""
        assert _tool_result_to_text("hello") == "hello"

    def test_list_of_text_dicts_joins_on_newlines(self) -> None:
        """The Anthropic ``[{"type": "text", "text": "..."}]`` shape should join with newlines."""
        result = _tool_result_to_text(
            [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ]
        )
        assert result == "first\nsecond"

    def test_list_with_unknown_items_falls_back_to_str(self) -> None:
        """Unknown dict shapes should round-trip via ``str`` rather than crash."""
        result = _tool_result_to_text(
            [
                {"type": "image", "url": "x"},
                "raw",
                42,
            ]
        )
        assert "image" in result
        assert "raw" in result
        assert "42" in result

    def test_arbitrary_object_falls_back_to_str(self) -> None:
        """Any other type should be coerced via ``str``."""
        assert _tool_result_to_text(42) == "42"


# ---------------------------------------------------------------------------
# Message → StreamEvent translation
# ---------------------------------------------------------------------------


class TestEventsFromMessage:
    """Every Claude SDK message kind should round-trip into the right ``StreamEvent``."""

    def test_assistant_text_block_yields_delta(self) -> None:
        """Text blocks should become ``delta`` events."""
        message = AssistantMessage(content=[TextBlock(text="hi")], model="claude")
        events = list(_events_from_message(message))
        assert events == [{"type": "delta", "content": "hi"}]

    def test_assistant_thinking_block_yields_thinking(self) -> None:
        """Thinking blocks should become ``thinking`` events."""
        message = AssistantMessage(
            content=[ThinkingBlock(thinking="reasoning", signature="sig")],
            model="claude",
        )
        events = list(_events_from_message(message))
        assert events == [{"type": "thinking", "content": "reasoning"}]

    def test_assistant_tool_use_block_yields_tool_use(self) -> None:
        """Tool use blocks should preserve id, name, and input."""
        message = AssistantMessage(
            content=[
                ToolUseBlock(id="tu_1", name="Bash", input={"cmd": "ls"}),
            ],
            model="claude",
        )
        events = list(_events_from_message(message))
        assert events == [
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {"cmd": "ls"},
                "tool_use_id": "tu_1",
                "display": {
                    "icon": "🛠",
                    "label": "Bash",
                    "present": "🛠 Running Bash (cmd)",
                    "compact": "Bash (cmd)",
                },
            }
        ]

    def test_assistant_tool_use_block_uses_display_map(self) -> None:
        """Tool use blocks should prefer shared display metadata when available."""
        from app.core.tools.display import make_tool_display

        message = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tu_1",
                    name="mcp__pawrrtal__read_file",
                    input={"path": "AGENTS.md"},
                ),
            ],
            model="claude",
        )
        display = make_tool_display(
            icon="📖",
            label="Read file",
            present=lambda args: f"📖 Reading {args['path']}",
            compact=lambda args: f"Read file -> {args['path']}",
        )

        events = list(_events_from_message(message, {"mcp__pawrrtal__read_file": display}))

        assert events[0]["display"] == {
            "icon": "📖",
            "label": "Read file",
            "present": "📖 Reading AGENTS.md",
            "compact": "Read file -> AGENTS.md",
        }

    def test_assistant_tool_result_block_yields_tool_result(self) -> None:
        """Tool result blocks inside an assistant message should produce a ``tool_result`` event."""
        message = AssistantMessage(
            content=[
                ToolResultBlock(tool_use_id="tu_1", content="output"),
            ],
            model="claude",
        )
        events = list(_events_from_message(message))
        assert events == [
            {
                "type": "tool_result",
                "tool_use_id": "tu_1",
                "content": "output",
                "is_error": False,
            }
        ]

    def test_assistant_mixed_blocks_preserve_order(self) -> None:
        """Multiple blocks in one message should yield events in order."""
        message = AssistantMessage(
            content=[
                ThinkingBlock(thinking="thinking", signature="sig"),
                TextBlock(text="first"),
                ToolUseBlock(id="t", name="Edit", input={}),
                TextBlock(text="last"),
            ],
            model="claude",
        )
        types = [event["type"] for event in _events_from_message(message)]
        assert types == ["thinking", "delta", "tool_use", "delta"]

    def test_assistant_error_field_emits_error_event(self) -> None:
        """An assistant message with ``error`` set should emit an extra error event."""
        message = AssistantMessage(
            content=[TextBlock(text="partial")],
            model="claude",
            error="rate_limit",
        )
        events = list(_events_from_message(message))
        assert events[0] == {"type": "delta", "content": "partial"}
        assert events[-1]["type"] == "error"
        assert "rate_limit" in events[-1]["content"]

    def test_user_message_with_tool_result_block_yields_tool_result(self) -> None:
        """``UserMessage`` content carrying tool results should be surfaced."""
        message = UserMessage(
            content=[ToolResultBlock(tool_use_id="tu_1", content="ok")],
        )
        events = list(_events_from_message(message))
        assert events == [
            {
                "type": "tool_result",
                "tool_use_id": "tu_1",
                "content": "ok",
                "is_error": False,
            }
        ]

    def test_user_message_with_string_content_emits_nothing(self) -> None:
        """Plain string user messages are echoes — no events should be emitted."""
        message = UserMessage(content="hello")
        assert list(_events_from_message(message)) == []

    def test_result_message_error_emits_error_event(self) -> None:
        """A ``ResultMessage`` with ``is_error=True`` should emit a single error event."""
        message = ResultMessage(
            subtype="error_max_turns",
            duration_ms=10,
            duration_api_ms=5,
            is_error=True,
            num_turns=1,
            session_id="s",
            stop_reason="max_turns",
        )
        events = list(_events_from_message(message))
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "max_turns" in events[0]["content"]

    def test_result_message_success_emits_nothing(self) -> None:
        """A successful ``ResultMessage`` is metadata only — no events."""
        message = ResultMessage(
            subtype="success",
            duration_ms=10,
            duration_api_ms=5,
            is_error=False,
            num_turns=1,
            session_id="s",
        )
        assert list(_events_from_message(message)) == []

    def test_rate_limit_rejected_emits_error_event(self) -> None:
        """A ``RateLimitEvent`` with status ``rejected`` should emit an error event."""
        event = RateLimitEvent(
            rate_limit_info=RateLimitInfo(status="rejected"),
            uuid="u",
            session_id="s",
        )
        events = list(_events_from_message(event))
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "rate limit" in events[0]["content"].lower()

    def test_rate_limit_warning_emits_nothing(self) -> None:
        """``allowed_warning`` is informational — no events should be emitted."""
        event = RateLimitEvent(
            rate_limit_info=RateLimitInfo(status="allowed_warning"),
            uuid="u",
            session_id="s",
        )
        assert list(_events_from_message(event)) == []

    def test_system_message_emits_nothing(self) -> None:
        """``SystemMessage`` carries CLI metadata only — no user-visible events."""
        message = SystemMessage(subtype="init", data={"info": True})
        assert list(_events_from_message(message)) == []

    def test_unknown_message_type_emits_nothing(self) -> None:
        """Unknown message types must not raise — they degrade to no events."""

        class Other:
            pass

        assert list(_events_from_message(Other())) == []


# ---------------------------------------------------------------------------
# ClaudeAgentOptions construction
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("force_new_session")
class TestProviderOptions:
    """:class:`ClaudeLLM` should build safe, predictable options."""

    @pytest.mark.anyio
    async def test_default_options_lock_down_tools_and_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """The default config should disable tools and isolate from filesystem settings."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM("claude-sonnet-4-6")

        await _collect(provider, "hello", conversation_id, user_id)

        assert captured, "query() must be invoked exactly once"
        options = captured[0]
        assert options.tools == []
        # Full isolation: setting_sources must be ``[]`` so the SDK
        # subprocess never reads CLAUDE.md, .claude/settings.json
        # (hooks), or .mcp.json from whatever directory it happens
        # to be running in. The workspace's CLAUDE.md is injected
        # via system_prompt= by ``turn_runner._workspace_system_prompt``
        # from the *correct* user workspace root.
        assert options.setting_sources == []
        assert options.permission_mode == "default"
        assert options.max_turns == 1
        # Default falls back to the shared `DEFAULT_AGENT_SYSTEM_PROMPT`
        # (provider-agnostic since PR #131 review).  Real chat traffic
        # gets the workspace's SOUL.md + AGENTS.md instead.
        assert options.system_prompt is not None and "chat application" in options.system_prompt

    @pytest.mark.anyio
    async def test_reasoning_effort_maps_to_sdk_effort(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """The UI reasoning selector should reach Claude Agent SDK options.

        Pawrrtal's ``extra-high`` saturates at ``high`` for Claude
        because the Claude API's adaptive thinking ``effort`` enum
        only documents ``low | medium | high``. The chat-router
        resolver normally maps this down before the provider runs
        — this test is the belt-and-braces in the provider itself.
        """
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM("claude-sonnet-4-6")

        await _collect(
            provider,
            "hello",
            conversation_id,
            user_id,
            reasoning_effort="extra-high",
        )

        assert captured[0].effort == "high"

    @pytest.mark.anyio
    async def test_first_turn_uses_session_id_not_resume(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """When the SDK session does not exist, options should set ``session_id``, not ``resume``."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM("claude-sonnet-4-6")

        await _collect(provider, "hello", conversation_id, user_id)

        options = captured[0]
        assert options.session_id == str(conversation_id)
        assert options.resume is None

    @pytest.mark.anyio
    async def test_subsequent_turn_resumes_existing_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        force_resume_session: None,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """When an SDK session exists, options should set ``resume``, not ``session_id``."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM("claude-sonnet-4-6")

        await _collect(provider, "follow up", conversation_id, user_id)

        options = captured[0]
        assert options.resume == str(conversation_id)
        assert options.session_id is None

    @pytest.mark.anyio
    async def test_oauth_token_is_forwarded_to_subprocess_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """A configured OAuth token should land in :attr:`ClaudeAgentOptions.env`."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM(
            "claude-sonnet-4-6",
            config=ClaudeLLMConfig(oauth_token="oat-secret"),
        )

        await _collect(provider, "hello", conversation_id, user_id)

        options = captured[0]
        assert options.env == {"CLAUDE_CODE_OAUTH_TOKEN": "oat-secret"}

    @pytest.mark.anyio
    async def test_no_oauth_token_means_empty_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """Without a configured token, ``options.env`` should be the SDK default (empty dict)."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM("claude-sonnet-4-6")

        await _collect(provider, "hello", conversation_id, user_id)

        assert captured[0].env == {}

    @pytest.mark.anyio
    async def test_extra_env_is_merged_with_oauth_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """Custom env vars should merge with the OAuth token."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM(
            "claude-sonnet-4-6",
            config=ClaudeLLMConfig(
                oauth_token="oat-secret",
                extra_env={"FOO": "bar"},
            ),
        )

        await _collect(provider, "hello", conversation_id, user_id)

        env = captured[0].env
        assert env["FOO"] == "bar"
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oat-secret"

    @pytest.mark.anyio
    async def test_model_is_resolved_through_map(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """The frontend model ID must round-trip through :func:`_resolve_sdk_model`."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM("claude-opus-4-7")

        await _collect(provider, "hello", conversation_id, user_id)

        assert captured[0].model == "claude-opus-4-7"

    @pytest.mark.anyio
    async def test_custom_config_overrides_apply(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """A custom :class:`ClaudeLLMConfig` should propagate to the SDK options."""
        captured = _patch_query(monkeypatch, _async_iter([]))
        provider = ClaudeLLM(
            "claude-sonnet-4-6",
            config=ClaudeLLMConfig(
                tools=["Read"],
                max_turns=3,
                permission_mode="plan",
                system_prompt="custom",
                cwd="/tmp/scoped",
            ),
        )

        await _collect(provider, "hello", conversation_id, user_id)

        options = captured[0]
        assert options.tools == ["Read"]
        assert options.max_turns == 3
        assert options.permission_mode == "plan"
        assert options.system_prompt == "custom"
        assert options.cwd == "/tmp/scoped"


# ---------------------------------------------------------------------------
# End-to-end stream behavior
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("force_new_session")
class TestProviderStreaming:
    """The provider should expose every translated SDK message as a stream event."""

    @pytest.mark.anyio
    async def test_text_message_streams_delta_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """A single text block round-trips into a single ``delta`` event."""
        _patch_query(
            monkeypatch,
            _async_iter(
                [
                    AssistantMessage(
                        content=[TextBlock(text="hello world")],
                        model="claude",
                    )
                ]
            ),
        )
        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )
        assert events == [{"type": "delta", "content": "hello world"}]

    @pytest.mark.anyio
    async def test_full_stream_emits_in_arrival_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """All message kinds combined should produce events in source order."""
        _patch_query(
            monkeypatch,
            _async_iter(
                [
                    SystemMessage(subtype="init", data={}),
                    AssistantMessage(
                        content=[
                            ThinkingBlock(thinking="t", signature="s"),
                            TextBlock(text="part 1"),
                            ToolUseBlock(id="tu", name="Read", input={"path": "x"}),
                        ],
                        model="claude",
                    ),
                    UserMessage(
                        content=[
                            ToolResultBlock(tool_use_id="tu", content="contents"),
                        ],
                    ),
                    AssistantMessage(
                        content=[TextBlock(text="part 2")],
                        model="claude",
                    ),
                    ResultMessage(
                        subtype="success",
                        duration_ms=1,
                        duration_api_ms=1,
                        is_error=False,
                        num_turns=1,
                        session_id="s",
                    ),
                ]
            ),
        )

        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )

        types = [event["type"] for event in events]
        assert types == [
            "thinking",
            "delta",
            "tool_use",
            "tool_result",
            "delta",
        ]
        # Spot-check the tool roundtrip carries the ID through both events.
        tool_use = next(event for event in events if event["type"] == "tool_use")
        tool_result = next(event for event in events if event["type"] == "tool_result")
        assert tool_use["tool_use_id"] == tool_result["tool_use_id"] == "tu"

    @pytest.mark.anyio
    async def test_empty_stream_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """An empty stream should not yield any events (the chat layer adds [DONE])."""
        _patch_query(monkeypatch, _async_iter([]))
        assert (
            await _collect(
                ClaudeLLM("claude-sonnet-4-6"),
                "hi",
                conversation_id,
                user_id,
            )
            == []
        )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("force_new_session")
class TestProviderErrors:
    """Every documented SDK error must be converted to a single ``error`` event."""

    @pytest.mark.anyio
    async def test_cli_not_found_becomes_error_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """A missing CLI binary should produce an actionable error event."""
        _patch_query(
            monkeypatch,
            _async_raises(CLINotFoundError(cli_path="/nope/claude")),
        )

        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "Claude Code CLI" in events[0]["content"]

    @pytest.mark.anyio
    async def test_cli_connection_error_becomes_error_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """Connection errors should round-trip with a stream-level error event."""
        _patch_query(monkeypatch, _async_raises(CLIConnectionError("subprocess died")))
        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "subprocess" in events[0]["content"].lower()

    @pytest.mark.anyio
    async def test_process_error_includes_exit_code_and_stderr(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """``ProcessError`` should surface its exit code and stderr in the event."""
        _patch_query(
            monkeypatch,
            _async_raises(ProcessError("crashed", exit_code=2, stderr="bad token")),
        )

        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "Exit code: 2" in events[0]["content"]
        assert "bad token" in events[0]["content"]

    @pytest.mark.anyio
    async def test_cli_json_decode_error_becomes_error_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """JSON decode errors should produce a stream-level error event."""
        _patch_query(
            monkeypatch,
            _async_raises(CLIJSONDecodeError("garbage", ValueError("nope"))),
        )

        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )

        assert len(events) == 1
        assert events[0]["type"] == "error"

    @pytest.mark.anyio
    async def test_generic_sdk_error_becomes_error_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """Any other :class:`ClaudeSDKError` should still be caught."""
        _patch_query(monkeypatch, _async_raises(ClaudeSDKError("weird")))

        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "weird" in events[0]["content"]

    @pytest.mark.anyio
    async def test_unrelated_exception_propagates(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """Non-SDK exceptions should surface to the chat handler — not be silently swallowed."""
        _patch_query(monkeypatch, _async_raises(RuntimeError("unexpected")))

        with pytest.raises(RuntimeError, match="unexpected"):
            await _collect(
                ClaudeLLM("claude-sonnet-4-6"),
                "hi",
                conversation_id,
                user_id,
            )


# ---------------------------------------------------------------------------
# Session probing fallback
# ---------------------------------------------------------------------------


class TestSessionProbeFallback:
    """If :func:`get_session_info` raises, the provider should treat the session as new."""

    @pytest.mark.anyio
    async def test_probe_failure_falls_back_to_new_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """A filesystem error during probing should not crash — first turn semantics apply."""

        def _boom(*_a: Any, **_k: Any) -> Any:
            raise OSError("permission denied")

        monkeypatch.setattr(cp_module, "get_session_info", _boom)
        captured = _patch_query(monkeypatch, _async_iter([]))

        await _collect(
            ClaudeLLM("claude-sonnet-4-6"),
            "hi",
            conversation_id,
            user_id,
        )

        assert captured[0].session_id == str(conversation_id)
        assert captured[0].resume is None


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


class TestFactory:
    """The factory should pull the OAuth token from settings into the provider."""

    def test_resolve_llm_pulls_oauth_token_from_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A token configured in settings must reach :class:`ClaudeLLMConfig`."""
        from app.core.providers import factory

        monkeypatch.setattr(factory.settings, "claude_code_oauth_token", "from-config")

        provider = factory.resolve_llm("anthropic/claude-sonnet-4-6")
        assert isinstance(provider, ClaudeLLM)
        assert provider._config.oauth_token == "from-config"

    def test_resolve_llm_omits_token_when_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A blank token in settings must coerce to ``None`` so we don't forward an empty value."""
        from app.core.providers import factory

        monkeypatch.setattr(factory.settings, "claude_code_oauth_token", "")

        provider = factory.resolve_llm("anthropic/claude-sonnet-4-6")
        assert isinstance(provider, ClaudeLLM)
        assert provider._config.oauth_token is None


# ---------------------------------------------------------------------------
# Scenario-level tests — realistic multi-message sequences via mock query
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("force_new_session")
class TestProviderScenarios:
    """End-to-end scenarios through ``ClaudeLLM.stream()`` using mock SDK output.

    These tests exercise the full ``provider.stream()`` path with realistic
    multi-message SDK sequences, verifying that event ordering, ID consistency,
    and content are correct across a complete tool-call round-trip.

    Unlike ``ScriptedStreamFn`` tests (which inject at the Python agent-loop
    seam), these tests inject at the ``claude_agent_sdk.query`` boundary
    because ``ClaudeLLM`` manages its own agent loop via the SDK subprocess.
    """

    @pytest.mark.anyio
    async def test_tool_call_round_trip_streams_events_in_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """A realistic tool-call sequence emits thinking → tool_use → tool_result → delta.

        Verifies:
        - All four event types are present in source order.
        - ``tool_use_id`` is consistent between tool_use and tool_result events.
        - Final text content is faithfully forwarded.
        """
        _patch_query(
            monkeypatch,
            _async_iter(
                [
                    AssistantMessage(
                        content=[
                            ThinkingBlock(thinking="let me check the files", signature="sig"),
                            ToolUseBlock(id="tu_ls", name="Bash", input={"cmd": "ls"}),
                        ],
                        model="claude",
                    ),
                    UserMessage(
                        content=[
                            ToolResultBlock(
                                tool_use_id="tu_ls",
                                content="file.txt\nother.txt",
                            )
                        ],
                    ),
                    AssistantMessage(
                        content=[TextBlock(text="Found 2 files.")],
                        model="claude",
                    ),
                    ResultMessage(
                        subtype="success",
                        duration_ms=100,
                        duration_api_ms=80,
                        is_error=False,
                        num_turns=2,
                        session_id="s",
                    ),
                ]
            ),
        )

        events = await _collect(
            ClaudeLLM(
                "claude-sonnet-4-6",
                config=ClaudeLLMConfig(tools=["Bash"], max_turns=2),
            ),
            "list files",
            conversation_id,
            user_id,
        )

        types = [e["type"] for e in events]
        assert types == ["thinking", "tool_use", "tool_result", "delta"]
        # tool_use_id must be consistent across both events.
        tool_use = next(e for e in events if e["type"] == "tool_use")
        tool_result = next(e for e in events if e["type"] == "tool_result")
        assert tool_use["tool_use_id"] == tool_result["tool_use_id"] == "tu_ls"
        assert tool_use["name"] == "Bash"
        assert "file.txt" in tool_result["content"]
        assert events[-1]["content"] == "Found 2 files."

    @pytest.mark.anyio
    async def test_parallel_tool_calls_preserve_both_ids(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """Two concurrent tool calls in one assistant message must both surface.

        Verifies that ``_events_from_message`` emits one ``tool_use`` event
        per ``ToolUseBlock``, not just the first one.
        """
        _patch_query(
            monkeypatch,
            _async_iter(
                [
                    AssistantMessage(
                        content=[
                            ToolUseBlock(id="tu_a", name="Read", input={"path": "a.txt"}),
                            ToolUseBlock(id="tu_b", name="Read", input={"path": "b.txt"}),
                        ],
                        model="claude",
                    ),
                    UserMessage(
                        content=[
                            ToolResultBlock(tool_use_id="tu_a", content="content-a"),
                            ToolResultBlock(tool_use_id="tu_b", content="content-b"),
                        ],
                    ),
                    AssistantMessage(
                        content=[TextBlock(text="done")],
                        model="claude",
                    ),
                ]
            ),
        )

        events = await _collect(
            ClaudeLLM(
                "claude-sonnet-4-6",
                config=ClaudeLLMConfig(tools=["Read"], max_turns=2),
            ),
            "read both files",
            conversation_id,
            user_id,
        )

        tool_use_ids = [e["tool_use_id"] for e in events if e["type"] == "tool_use"]
        tool_result_ids = [e["tool_use_id"] for e in events if e["type"] == "tool_result"]
        assert sorted(tool_use_ids) == ["tu_a", "tu_b"]
        assert sorted(tool_result_ids) == ["tu_a", "tu_b"]

    @pytest.mark.anyio
    async def test_max_turns_exhausted_surfaces_error_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        conversation_id: UUID,
        user_id: UUID,
    ) -> None:
        """When the SDK exhausts ``max_turns``, an error event must surface in the stream.

        This is the Claude equivalent of ``agent_terminated`` from the Python
        agent loop.  The ``ResultMessage(is_error=True, stop_reason='max_turns')``
        must produce exactly one error event.
        """
        _patch_query(
            monkeypatch,
            _async_iter(
                [
                    AssistantMessage(
                        content=[TextBlock(text="partial answer")],
                        model="claude",
                    ),
                    ResultMessage(
                        subtype="error_max_turns",
                        duration_ms=500,
                        duration_api_ms=450,
                        is_error=True,
                        num_turns=1,
                        session_id="s",
                        stop_reason="max_turns",
                    ),
                ]
            ),
        )

        events = await _collect(
            ClaudeLLM("claude-sonnet-4-6", config=ClaudeLLMConfig(max_turns=1)),
            "long task",
            conversation_id,
            user_id,
        )

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "max_turns" in error_events[0]["content"]
