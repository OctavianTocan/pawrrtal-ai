"""LCM expand_query — bounded deep-recall via a single focused LLM call.

Design
------
The upstream lossless-claw plugin spawns an OpenClaw sub-agent that walks
the full summary DAG.  We use our own infrastructure: instead of a real
sub-agent, we make one focused LLM call with the *complete* conversation
history — all LCMContextItems resolved in ordinal order, not just the
fresh tail — and return its answer.

This is "bounded" in the sense that:
- It is a single-turn call, not a multi-turn loop.
- Input is capped at MAX_EXPAND_ITEMS items so we don't exceed a model
  context window even for very long conversations.
- Errors are surfaced as descriptive strings, not exceptions, so the
  calling agent can self-correct.

When to use it vs. lcm_grep
-----------------------------
* ``lcm_grep``         — keyword/phrase search; cheap; returns excerpts.
* ``lcm_describe``     — read one summary node in full; very cheap.
* ``lcm_expand_query`` — "answer a question about the full history"; slower
                         (one extra LLM call) but gives a synthesised answer.
                         Use when grep returns an excerpt and you need the
                         full story, or when the answer spans multiple
                         compacted nodes.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import settings as _settings
from app.lcm.summarization import _collect_stream, _format_turns
from app.models import ChatMessage, LCMContextItem, LCMSummary
from app.turns.pipeline.subcalls import LlmSubcall, stream_llm_subcall

# Hard cap so we never build a prompt larger than the model can handle.
_MAX_EXPAND_ITEMS = 500

_EXPAND_SYSTEM_PROMPT = """\
You are a recall assistant.  You have access to the full history of a
conversation (raw messages and compacted summaries, in chronological order).
Answer the user's question based ONLY on what is present in this history.
If the answer is not in the history, say so explicitly.
Be concise and cite specific turns or summary nodes when relevant."""


async def lcm_expand_query(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    model_id: str,
    prompt: str,
) -> str:
    """Answer *prompt* by running a focused LLM call over the full history.

    Fetches ALL ``lcm_context_items`` for *conversation_id* (up to
    ``_MAX_EXPAND_ITEMS``), resolves each one to its backing content,
    assembles a transcript, and calls the model with *prompt* as the
    user turn.

    Args:
        session: Open async database session.
        conversation_id: Conversation to expand.
        user_id: Used to resolve provider API keys.
        model_id: The model to use for the expansion call.  Falls back to
            ``settings.lcm_summary_model`` if non-empty, then to model_id.
        prompt: The question / retrieval task for the sub-call.

    Returns:
        The model's synthesised answer, or an error string if the call
        fails or no history exists.
    """
    if not prompt.strip():
        return "lcm_expand_query: empty prompt — nothing to answer."

    turns = await _collect_full_history_turns(session, conversation_id=conversation_id)
    if turns is None:
        return (
            "lcm_expand_query: no conversation history found.  "
            "The conversation may be empty or LCM ingest has not run yet."
        )
    if not turns:
        return "lcm_expand_query: resolved to an empty history — nothing to answer."

    expansion_prompt = f"CONVERSATION HISTORY:\n{_format_turns(turns)}\n\nQUESTION:\n{prompt}"
    expand_model = _settings.lcm_summary_model or model_id

    try:
        stream = stream_llm_subcall(
            LlmSubcall(
                model_id=expand_model,
                question=expansion_prompt,
                conversation_id=uuid.uuid4(),  # isolated; not a real turn
                user_id=user_id,
                history=None,
                tools=[],
                system_prompt=_EXPAND_SYSTEM_PROMPT,
            )
        )
        answer = await _collect_stream(stream)
        if answer:
            return answer
        return "lcm_expand_query: the model returned an empty response."
    except Exception as exc:
        return f"lcm_expand_query: expansion call failed — {exc}"


async def _collect_full_history_turns(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
) -> list[dict[str, str]] | None:
    """Resolve every LCM context item into a ``{role, content}`` turn list.

    Returns ``None`` when there are no context items at all (caller renders
    the explicit "no history" message), or an empty list when items exist
    but none resolve to non-empty content.  Bounded by
    ``_MAX_EXPAND_ITEMS`` so a runaway conversation can't blow the model's
    context window.
    """
    items_result = await session.execute(
        select(LCMContextItem)
        .where(LCMContextItem.conversation_id == conversation_id)
        .order_by(LCMContextItem.ordinal.asc())
        .limit(_MAX_EXPAND_ITEMS)
    )
    items = list(items_result.scalars().all())
    if not items:
        return None

    message_ids = [i.item_id for i in items if i.item_kind == "message"]
    summary_ids = [i.item_id for i in items if i.item_kind == "summary"]

    messages_by_id: dict[uuid.UUID, ChatMessage] = {}
    if message_ids:
        m_res = await session.execute(select(ChatMessage).where(ChatMessage.id.in_(message_ids)))
        messages_by_id = {m.id: m for m in m_res.scalars().all()}

    summaries_by_id: dict[uuid.UUID, LCMSummary] = {}
    if summary_ids:
        s_res = await session.execute(select(LCMSummary).where(LCMSummary.id.in_(summary_ids)))
        summaries_by_id = {s.id: s for s in s_res.scalars().all()}

    turns: list[dict[str, str]] = []
    for item in items:
        turn = _resolve_item_to_turn(item, messages_by_id, summaries_by_id)
        if turn is not None:
            turns.append(turn)
    return turns


def _resolve_item_to_turn(
    item: LCMContextItem,
    messages_by_id: dict[uuid.UUID, ChatMessage],
    summaries_by_id: dict[uuid.UUID, LCMSummary],
) -> dict[str, str] | None:
    """Map one ``LCMContextItem`` to its ``{role, content}`` shape, or ``None`` to drop."""
    if item.item_kind == "message":
        msg = messages_by_id.get(item.item_id)
        if msg and msg.role in {"user", "assistant"} and msg.content:
            return {"role": msg.role, "content": msg.content}
        return None
    if item.item_kind == "summary":
        summ = summaries_by_id.get(item.item_id)
        if summ and summ.content:
            return {
                "role": "user",
                "content": f"[Compacted summary, depth={summ.depth}]\n{summ.content}",
            }
    return None
