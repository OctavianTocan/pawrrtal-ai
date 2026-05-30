"""Gemini provider-native replay helpers.

Split out of ``gemini_provider`` to keep that module under the 500-line
file budget.  All helpers are private — the public surface lives on
``gemini_provider`` (``_build_gemini_contents`` consumes
:func:`replay_content_for`; ``make_gemini_stream_fn`` consumes
:func:`function_call_content_for`).

Background
----------
Gemini-3 / Vertex requires that ``thought_signature`` bytes from a
prior turn be replayed verbatim on the follow-up tool turn — see
https://ai.google.dev/gemini-api/docs/thought-signatures.  Pawrrtal's
agent loop is provider-neutral, so the bytes ride in an opaque
``provider_state["gemini"]["model_content"]`` slot on the
``AssistantMessage`` and the StreamFn captures them on the producing
turn.
"""

from __future__ import annotations

from typing import Any

from google.genai import types as gtypes

from app.agents.types import AgentMessage


def replay_content_for(msg: AgentMessage) -> gtypes.Content | None:
    """Return the saved native ``ModelContent`` from ``msg`` if present.

    Pawrrtal stores Gemini's original ``ModelContent`` on the assistant
    message under ``provider_state["gemini"]["model_content"]`` (set by
    :func:`make_gemini_stream_fn`).  Replaying it verbatim keeps the
    ``thought_signature`` bytes intact, which Gemini-3 / Vertex require
    on follow-up tool turns or the request 4xx's.
    """
    if msg.get("role") != "assistant":
        return None
    state = msg.get("provider_state") or {}
    gemini_state = state.get("gemini") if isinstance(state, dict) else None
    if not isinstance(gemini_state, dict):
        return None
    content = gemini_state.get("model_content")
    if isinstance(content, gtypes.Content):
        return content
    return None


def function_call_content_for(chunk: Any) -> gtypes.Content | None:
    """Return the first candidate's ``ModelContent`` when it contains a function call.

    The native ``ModelContent`` carries ``thought_signature`` bytes that
    Gemini-3 / Vertex demand on follow-up tool turns; saving it lets us
    replay the exact part instead of reconstructing a lossy
    ``function_call`` from name + args.
    """
    for candidate in chunk.candidates or []:
        content = getattr(candidate, "content", None)
        if not isinstance(content, gtypes.Content):
            continue
        parts = content.parts
        if not parts:
            continue
        if any(part.function_call for part in parts):
            return content
    return None
