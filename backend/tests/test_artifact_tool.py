"""Unit and scenario tests for the ``render_artifact`` tool + chat-router helper.

Covers three layers:

1. **Wire-shape validation** (:func:`build_artifact`) — pure-Python, no I/O.
2. **AgentTool wrapper** (:func:`make_artifact_tool`) — execute callback
   contract: returns corrective strings instead of raising so the LLM can
   self-correct on the next turn.
3. **Chat-router helper** (``_maybe_artifact_event``) — the seam that turns
   a ``tool_use`` from the model into the structured ``artifact`` SSE event
   the frontend renders.
4. **End-to-end agent-loop scenarios** (``TestArtifactToolScenarios``) —
   ``ScriptedStreamFn`` exercises the real ``agent_loop``, safety layer, and
   tool-execution code without API calls.  These are the load-bearing tests:
   they prove the tool is wired in correctly and behaves under realistic
   multi-turn conversation conditions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.providers.base import StreamEvent
from app.core.tools.artifact import (
    ArtifactValidationError,
    build_artifact,
    llm_summary_for,
)
from app.core.tools.artifact_agent import (
    ARTIFACT_TOOL_NAME,
    make_artifact_tool,
)

_VALID_SPEC = {
    "root": "page",
    "elements": {
        "page": {
            "type": "Page",
            "props": {"title": "demo", "accent": "cat"},
            "children": ["heading"],
        },
        "heading": {
            "type": "Heading",
            "props": {"text": "Hello"},
            "children": [],
        },
    },
}


# ---------------------------------------------------------------------------
# build_artifact — wire-shape validation
# ---------------------------------------------------------------------------


def test_build_artifact_returns_payload_with_minted_id() -> None:
    payload = build_artifact(title="Demo", spec=_VALID_SPEC)

    assert payload["title"] == "Demo"
    assert payload["spec"] is _VALID_SPEC
    assert payload["id"].startswith("art_")
    # The id is uuid4 hex truncated to 12 chars; the prefix shouldn't bleed in.
    assert len(payload["id"]) == 4 + 12  # "art_" + 12 hex chars


def test_build_artifact_rejects_blank_title() -> None:
    with pytest.raises(ArtifactValidationError, match="title"):
        build_artifact(title="   ", spec=_VALID_SPEC)


def test_build_artifact_rejects_overlong_title() -> None:
    with pytest.raises(ArtifactValidationError, match=r"≤200"):
        build_artifact(title="x" * 201, spec=_VALID_SPEC)


def test_build_artifact_rejects_missing_root() -> None:
    bad = {"elements": _VALID_SPEC["elements"]}
    with pytest.raises(ArtifactValidationError, match="root"):
        build_artifact(title="Demo", spec=bad)


def test_build_artifact_rejects_root_pointing_outside_elements() -> None:
    bad = {"root": "ghost", "elements": _VALID_SPEC["elements"]}
    with pytest.raises(ArtifactValidationError, match="not present"):
        build_artifact(title="Demo", spec=bad)


def test_build_artifact_rejects_non_string_children() -> None:
    bad = {
        "root": "page",
        "elements": {
            "page": {
                "type": "Page",
                "props": {},
                "children": [{"not": "a string"}],
            }
        },
    }
    with pytest.raises(ArtifactValidationError, match="children"):
        build_artifact(title="Demo", spec=bad)


# ---------------------------------------------------------------------------
# llm_summary_for — what the model sees back
# ---------------------------------------------------------------------------


def test_llm_summary_does_not_echo_spec_back_to_model() -> None:
    payload = build_artifact(title="My title", spec=_VALID_SPEC)
    summary = llm_summary_for(payload)

    assert payload["id"] in summary
    assert payload["title"] in summary
    # The summary is the on-ramp to the LLM's next turn; including the
    # spec here would inflate context for no benefit.
    assert "Heading" not in summary
    assert "elements" not in summary


# ---------------------------------------------------------------------------
# AgentTool wrapper
# ---------------------------------------------------------------------------


def test_agent_tool_metadata() -> None:
    tool = make_artifact_tool()
    assert tool.name == ARTIFACT_TOOL_NAME
    assert "title" in tool.parameters["required"]
    assert "spec" in tool.parameters["required"]
    assert "preview card" in tool.description.lower()


def test_agent_tool_execute_returns_summary_on_valid_call() -> None:
    tool = make_artifact_tool()
    result = asyncio.run(tool.execute(tool_call_id="t1", title="Demo", spec=_VALID_SPEC))
    assert result.startswith("Artifact rendered")
    assert "art_" in result


def test_agent_tool_execute_returns_corrective_string_on_bad_spec() -> None:
    tool = make_artifact_tool()
    result = asyncio.run(tool.execute(tool_call_id="t1", title="Demo", spec="not a dict"))
    # Should be human-readable so the LLM can self-correct, not raise.
    assert "Error" in result
    assert "render_artifact again" in result


# ---------------------------------------------------------------------------
# Surface-gated description — interactive widget catalog is web/electron only
# ---------------------------------------------------------------------------


def test_interactive_catalog_is_advertised_on_web_surface() -> None:
    """Web surface sees the interactive components in the spec schema description
    and the description blurb so the model knows it can emit them.
    """
    tool = make_artifact_tool(surface="web")
    spec_desc = tool.parameters["properties"]["spec"]["description"]
    # Read-only catalog is always present.
    assert "Heading" in spec_desc
    # Interactive components are advertised on web.
    assert "ActionButton" in spec_desc
    assert "ChoiceGroup" in spec_desc
    assert "TextField" in spec_desc
    assert "NumberField" in spec_desc
    # The interactive blurb should appear in the tool description itself.
    assert "INTERACTIVE" in tool.description


def test_interactive_catalog_is_advertised_on_electron_surface() -> None:
    """Electron mirrors web — the spec schema must mention interactive widgets."""
    tool = make_artifact_tool(surface="electron")
    spec_desc = tool.parameters["properties"]["spec"]["description"]
    assert "ActionButton" in spec_desc


def test_interactive_catalog_is_hidden_on_telegram_surface() -> None:
    """Telegram is text-only — advertising interactive widgets would invite the
    model to emit unrenderable controls.
    """
    tool = make_artifact_tool(surface="telegram")
    spec_desc = tool.parameters["properties"]["spec"]["description"]
    # Read-only catalog is still present.
    assert "Heading" in spec_desc
    # Interactive components are NOT mentioned.
    assert "ActionButton" not in spec_desc
    assert "ChoiceGroup" not in spec_desc
    assert "TextField" not in spec_desc
    assert "NumberField" not in spec_desc
    assert "INTERACTIVE" not in tool.description


def test_interactive_catalog_is_hidden_when_surface_unset() -> None:
    """No surface (background jobs, tests) defaults to the conservative
    read-only catalog so a stray usage never invites unrenderable widgets.
    """
    tool = make_artifact_tool()
    spec_desc = tool.parameters["properties"]["spec"]["description"]
    assert "ActionButton" not in spec_desc
    assert "INTERACTIVE" not in tool.description


def test_execute_validation_is_surface_independent() -> None:
    """Validation lives in build_artifact, not the description — Telegram tools
    must accept the same shapes as web tools so a workspace re-issued against
    Telegram doesn't suddenly reject otherwise-valid specs.
    """
    web_tool = make_artifact_tool(surface="web")
    tg_tool = make_artifact_tool(surface="telegram")

    web_result = asyncio.run(web_tool.execute(tool_call_id="t", title="X", spec=_VALID_SPEC))
    tg_result = asyncio.run(tg_tool.execute(tool_call_id="t", title="X", spec=_VALID_SPEC))

    assert web_result.startswith("Artifact rendered")
    assert tg_result.startswith("Artifact rendered")


# ---------------------------------------------------------------------------
# Chat-router helper
# ---------------------------------------------------------------------------


def test_maybe_artifact_event_emits_for_render_artifact_tool_use() -> None:
    from app.api.chat import _maybe_artifact_event

    event: StreamEvent = {
        "type": "tool_use",
        "tool_use_id": "tu_42",
        "name": ARTIFACT_TOOL_NAME,
        "input": {"title": "Hello", "spec": _VALID_SPEC},
    }

    out = _maybe_artifact_event(event)
    assert out is not None
    assert out["type"] == "artifact"
    artifact = out["artifact"]
    assert artifact["title"] == "Hello"
    assert artifact["spec"] == _VALID_SPEC
    assert artifact["id"].startswith("art_")
    assert artifact["tool_use_id"] == "tu_42"


def test_maybe_artifact_event_returns_none_for_other_tools() -> None:
    from app.api.chat import _maybe_artifact_event

    event: StreamEvent = {
        "type": "tool_use",
        "tool_use_id": "tu_1",
        "name": "exa_search",
        "input": {"query": "anything"},
    }
    assert _maybe_artifact_event(event) is None


def test_maybe_artifact_event_returns_none_for_invalid_spec() -> None:
    from app.api.chat import _maybe_artifact_event

    event: StreamEvent = {
        "type": "tool_use",
        "tool_use_id": "tu_1",
        "name": ARTIFACT_TOOL_NAME,
        "input": {"title": "", "spec": _VALID_SPEC},
    }
    # Bad title — silent None so the agent's own retry loop kicks in via
    # the tool's error string, instead of half-emitting a broken event.
    assert _maybe_artifact_event(event) is None


def test_maybe_artifact_event_returns_none_for_non_tool_events() -> None:
    from app.api.chat import _maybe_artifact_event

    delta: StreamEvent = {"type": "delta", "content": "hello"}
    assert _maybe_artifact_event(delta) is None


# ---------------------------------------------------------------------------
# build_agent_tools integration — render_artifact must be registered
# ---------------------------------------------------------------------------


def test_artifact_tool_is_registered_in_build_agent_tools(tmp_path: Path) -> None:
    """The render_artifact tool must appear in the live tool catalogue.

    This test guards against accidental removal from ``build_agent_tools``.
    It also verifies no duplicate tool names are registered.
    """

    from app.core.agent_loop.tools import build_agent_tools

    tools = build_agent_tools(workspace_root=tmp_path)
    tool_names = [t.name for t in tools]

    assert ARTIFACT_TOOL_NAME in tool_names, (
        f"render_artifact missing from build_agent_tools; got: {tool_names}"
    )
    # No duplicate tool names — the agent loop does a dict-lookup by name.
    assert len(tool_names) == len(set(tool_names)), (
        f"Duplicate tool names in catalogue: {tool_names}"
    )


# ---------------------------------------------------------------------------
# End-to-end agent-loop scenario tests
#
# These tests use ``ScriptedStreamFn`` to drive the real agent_loop through
# deterministic sequences.  They are the authoritative proof that
# render_artifact is wired correctly end-to-end — not just that the
# functions exist, but that the loop actually calls the tool, feeds the
# result back to the LLM context, and emits the expected AgentEvents.
# ---------------------------------------------------------------------------


class TestArtifactToolScenarios:
    """Scenario tests: render_artifact through the real agent_loop."""

    @pytest.mark.anyio
    async def test_single_artifact_happy_path(self) -> None:
        """Agent calls render_artifact once with a valid spec.

        Verifies:
        - The tool executes without error (is_error=False on the ToolResultEvent).
        - The LLM sees the confirmation summary on the next turn.
        - The agent finishes cleanly in 2 LLM calls.
        """
        from tests.agent_harness import (
            make_recording_stream_fn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        script = make_recording_stream_fn(
            [
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "Demo Dashboard", "spec": _VALID_SPEC},
                    turn_id="art-tc-1",
                ),
                text_turn("Here's your dashboard!"),
            ]
        )

        events = await run_scenario(script, tools=[make_artifact_tool()])

        assert script.call_count == 2

        # Tool result must not be marked as error.
        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_result_events) == 1
        tr = tool_result_events[0]
        assert tr["tool_call_id"] == "art-tc-1"
        assert tr["is_error"] is False
        assert "art_" in tr["content"], "Confirmation should contain the minted id"
        assert "Demo Dashboard" in tr["content"]

        # The second LLM call must see the tool result in its message context.
        second_turn_messages = script.messages_seen[1]
        tool_result_msgs = [m for m in second_turn_messages if m["role"] == "toolResult"]
        assert len(tool_result_msgs) == 1
        assert "Artifact rendered" in tool_result_msgs[0]["content"][0]["text"]

    @pytest.mark.anyio
    async def test_agent_self_corrects_after_bad_spec(self) -> None:
        """Agent calls render_artifact with a bad spec, sees the corrective error,
        then retries with a valid spec and succeeds.

        The artifact tool returns corrective error strings (never raises) so
        the LLM can self-correct.  This test proves the whole retry cycle works
        end-to-end through the real loop.
        """
        from tests.agent_harness import (
            make_recording_stream_fn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        # Bad spec: root points to an element that doesn't exist in elements.
        bad_spec = {"root": "ghost", "elements": _VALID_SPEC["elements"]}

        script = make_recording_stream_fn(
            [
                # Turn 1: bad call.
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "My Card", "spec": bad_spec},
                    turn_id="art-tc-bad",
                ),
                # Turn 2: agent receives corrective string and retries.
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "My Card", "spec": _VALID_SPEC},
                    turn_id="art-tc-good",
                ),
                # Turn 3: agent says done.
                text_turn("Artifact is ready!"),
            ]
        )

        events = await run_scenario(script, tools=[make_artifact_tool()])

        assert script.call_count == 3

        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_result_events) == 2

        bad_tr, good_tr = tool_result_events
        # First call: validation error string, but NOT a hard error — the tool
        # returns a corrective string, so is_error stays False.
        assert bad_tr["is_error"] is False
        assert "Error" in bad_tr["content"] or "error" in bad_tr["content"].lower()
        assert "render_artifact again" in bad_tr["content"]

        # Second call: succeeds.
        assert good_tr["is_error"] is False
        assert "Artifact rendered" in good_tr["content"]
        assert "My Card" in good_tr["content"]

        # By turn 3 the LLM context should carry both tool results.
        third_turn_msgs = script.messages_seen[2]
        tool_results_in_ctx = [m for m in third_turn_msgs if m["role"] == "toolResult"]
        assert len(tool_results_in_ctx) == 2

    @pytest.mark.anyio
    async def test_artifact_alongside_other_tools(self) -> None:
        """render_artifact can coexist in a tool list with other tools.

        Scenario: the agent first uses an echo tool (e.g. for a search), then
        calls render_artifact to display the result as a card.  Both tools must
        execute correctly and their results must accumulate in LLM context.
        """
        from tests.agent_harness import (
            echo_tool,
            make_recording_stream_fn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        script = make_recording_stream_fn(
            [
                # Turn 1: agent calls echo (simulating any other tool).
                tool_call_turn("echo", {"value": "search result"}, turn_id="echo-1"),
                # Turn 2: agent renders the result as an artifact.
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "Search Summary", "spec": _VALID_SPEC},
                    turn_id="art-1",
                ),
                # Turn 3: agent is done.
                text_turn("Done."),
            ]
        )

        events = await run_scenario(
            script,
            tools=[echo_tool("echo"), make_artifact_tool()],
        )

        assert script.call_count == 3

        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_result_events) == 2

        echo_tr = tool_result_events[0]
        assert echo_tr["tool_call_id"] == "echo-1"
        assert echo_tr["is_error"] is False
        assert "search result" in echo_tr["content"]

        art_tr = tool_result_events[1]
        assert art_tr["tool_call_id"] == "art-1"
        assert art_tr["is_error"] is False
        assert "Artifact rendered" in art_tr["content"]

        # Final LLM call sees both tool results.
        final_ctx_tool_results = [m for m in script.messages_seen[2] if m["role"] == "toolResult"]
        assert len(final_ctx_tool_results) == 2

    @pytest.mark.anyio
    async def test_multiple_artifacts_in_single_conversation(self) -> None:
        """Agent can render two separate artifacts in the same conversation.

        Each artifact call should be independent: different ids, different titles,
        both confirmed to the LLM.
        """
        from tests.agent_harness import (
            make_recording_stream_fn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        spec_b = {
            "root": "stat",
            "elements": {
                "stat": {
                    "type": "StatPill",
                    "props": {"label": "Users", "value": "1 000"},
                    "children": [],
                }
            },
        }

        script = make_recording_stream_fn(
            [
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "Overview", "spec": _VALID_SPEC},
                    turn_id="art-first",
                ),
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "Stats", "spec": spec_b},
                    turn_id="art-second",
                ),
                text_turn("Both artifacts delivered."),
            ]
        )

        events = await run_scenario(script, tools=[make_artifact_tool()])

        assert script.call_count == 3

        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 2

        assert all(tr["is_error"] is False for tr in tool_results)
        first_content = tool_results[0]["content"]
        second_content = tool_results[1]["content"]

        assert "Overview" in first_content
        assert "Stats" in second_content
        # Each must get its own unique artifact id.
        assert "art_" in first_content
        assert "art_" in second_content
        # Different titles → different confirmations.
        assert first_content != second_content

    @pytest.mark.anyio
    async def test_agent_loop_emits_correct_event_sequence_for_artifact(self) -> None:
        """The agent_loop emits tool_call_start → tool_call_end → tool_result
        for an artifact call — same sequencing contract as all other tools.
        """
        from tests.agent_harness import (
            ScriptedStreamFn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        script = ScriptedStreamFn(
            [
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "Seq Test", "spec": _VALID_SPEC},
                    turn_id="seq-tc",
                ),
                text_turn("done"),
            ]
        )

        events = await run_scenario(script, tools=[make_artifact_tool()])

        types_in_order = [e["type"] for e in events]
        tcs_idx = types_in_order.index("tool_call_start")
        tce_idx = types_in_order.index("tool_call_end")
        tr_idx = types_in_order.index("tool_result")

        assert tcs_idx < tce_idx < tr_idx, (
            f"Expected tool_call_start < tool_call_end < tool_result; "
            f"got positions {tcs_idx}, {tce_idx}, {tr_idx}"
        )

        # The tool_call_end must name the artifact tool.
        tce = next(e for e in events if e["type"] == "tool_call_end")
        assert tce["name"] == ARTIFACT_TOOL_NAME
        assert tce["tool_call_id"] == "seq-tc"

    @pytest.mark.anyio
    async def test_unknown_artifact_tool_name_is_not_found(self) -> None:
        """If the tool name doesn't match any registered tool, agent_loop yields
        is_error=True with a 'not found' message — render_artifact name must be
        spelled exactly as ARTIFACT_TOOL_NAME in the script.
        """
        from tests.agent_harness import (
            ScriptedStreamFn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        script = ScriptedStreamFn(
            [
                tool_call_turn(
                    "render_ARTIFACT",  # wrong capitalisation — not registered
                    {"title": "X", "spec": _VALID_SPEC},
                ),
                text_turn("done"),
            ]
        )

        events = await run_scenario(script, tools=[make_artifact_tool()])

        tool_result_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_result_events) == 1
        assert tool_result_events[0]["is_error"] is True
        assert "not found" in tool_result_events[0]["content"]

    @pytest.mark.anyio
    async def test_empty_title_yields_corrective_error_not_loop_crash(self) -> None:
        """Blank title is the most likely LLM mistake.  The agent_loop must NOT
        crash — it must receive the corrective string and continue normally.
        """
        from tests.agent_harness import (
            ScriptedStreamFn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        script = ScriptedStreamFn(
            [
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "", "spec": _VALID_SPEC},
                ),
                text_turn("I see the error, fixed."),
            ]
        )

        events = await run_scenario(script, tools=[make_artifact_tool()])

        # Loop must complete without exception.
        end_events = [e for e in events if e["type"] == "agent_end"]
        assert len(end_events) == 1

        tr = next(e for e in events if e["type"] == "tool_result")
        # Title validation error → corrective string, not crash.
        assert tr["is_error"] is False
        assert "title" in tr["content"].lower() or "Error" in tr["content"]

    @pytest.mark.anyio
    async def test_spec_missing_elements_yields_corrective_string(self) -> None:
        """Missing 'elements' key is another common model mistake.  Loop must
        feed the corrective string back cleanly.
        """
        from tests.agent_harness import (
            ScriptedStreamFn,
            run_scenario,
            text_turn,
            tool_call_turn,
        )

        bad_spec = {"root": "page"}  # elements key missing entirely

        script = ScriptedStreamFn(
            [
                tool_call_turn(
                    ARTIFACT_TOOL_NAME,
                    {"title": "Missing Elements", "spec": bad_spec},
                ),
                text_turn("Understood the error."),
            ]
        )

        events = await run_scenario(script, tools=[make_artifact_tool()])

        tr = next(e for e in events if e["type"] == "tool_result")
        assert tr["is_error"] is False
        assert "elements" in tr["content"].lower()
