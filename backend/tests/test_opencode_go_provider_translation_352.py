"""Per-provider translation tests for OpenCode Go (#352 L4).

L4 of the #352 plan asks for "realistic raw provider event →
StreamEvent" tests *per provider* (no parametrised ABC — providers
genuinely differ in their wire shapes). The xAI surface is already
covered by ``test_xai_provider_translation.py``; Gemini's
``split_chunk_text`` / ``tool_calls_from_chunk`` / ``read_reasoning``
are covered by ``test_gemini_stream_fn.py``. This file fills the
OpenCode Go gap.

The interesting case the issue plan calls out specifically: a 401
must reach the user as an ``error`` event, NOT a text-delta with
"OpenCode Go error: …" pretending to be the assistant's reply. PR
#371 added the early ``XAI_API_KEY``-missing → ``error`` shortcut
in ``opencode_go_provider.py``; this test pins that contract so a
future refactor can't regress it.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.core.providers.opencode_go_provider import OpencodeGoLLM, OpencodeGoLLMConfig


@pytest.mark.anyio
async def test_missing_api_key_surfaces_as_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``OPENCODE_API_KEY`` configured → ``error`` event, not text-delta.

    Reproduces the #350 root cause: when the gateway has no key, the
    provider used to send ``api_key="missing"`` to the OpenAI client,
    take a 401, catch it in the stream-fn's broad ``except``, and
    yield a text-delta carrying ``"OpenCode Go error: ..."``. The
    legacy Telegram text path then frequently dropped that delta
    (#346), producing "no reply at all" for the user.

    The fix in PR #371 short-circuits at the top of
    ``OpencodeGoLLM.stream`` with an explicit
    ``StreamEvent(type="error", content=...)`` before the agent loop
    runs. This test pins that contract.
    """
    monkeypatch.setattr(settings, "opencode_api_key", "")

    llm = OpencodeGoLLM(
        model_id="kimi-k2.6",
        config=OpencodeGoLLMConfig(
            cost_per_mtok_in_usd=0.0,
            cost_per_mtok_out_usd=0.0,
        ),
        workspace_root=None,
    )

    events = [
        event
        async for event in llm.stream(
            question="hi",
            conversation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
    ]

    assert len(events) == 1, f"Expected single error event, got {events}"
    error_event = events[0]
    assert error_event["type"] == "error", (
        f"Missing-key path leaked through agent_loop instead of "
        f"surfacing as error; got {error_event!r}"
    )
    assert "OpenCode" in str(error_event.get("content", ""))


@pytest.mark.anyio
async def test_missing_api_key_does_not_invoke_agent_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The missing-key shortcut must run BEFORE ``agent_loop`` is touched.

    Side-by-side guard against the regression where someone "fixes"
    the symptom by yielding an error event from inside the agent
    loop's safety budget — three 401s burn before the user sees
    anything. The shortcut at the top of ``stream()`` must bypass
    ``agent_loop`` entirely when the key is empty.
    """
    monkeypatch.setattr(settings, "opencode_api_key", "")

    llm = OpencodeGoLLM(
        model_id="kimi-k2.6",
        config=OpencodeGoLLMConfig(
            cost_per_mtok_in_usd=0.0,
            cost_per_mtok_out_usd=0.0,
        ),
        workspace_root=None,
    )

    with patch("app.core.providers.opencode_go_provider.agent_loop") as patched_loop:
        events = [
            event
            async for event in llm.stream(
                question="hi",
                conversation_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )
        ]

    assert len(events) == 1
    assert events[0]["type"] == "error"
    patched_loop.assert_not_called(), (
        "OpencodeGoLLM ran the agent loop on a missing key — the "
        "fail-fast shortcut regressed."
    )
