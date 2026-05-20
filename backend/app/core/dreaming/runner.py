"""Dreaming-pass runner — drives one :class:`DreamingJob` end-to-end (#341).

Per the ADR at
``frontend/content/docs/handbook/decisions/2026-05-20-dreaming-background-reflection.mdx``,
each pass:

1. Reads the chat history window the job points at
   (``session_end`` → last N messages on the conversation;
   ``daily_rollup`` → last 24h across all of the user's conversations).
2. Renders the dreaming prompt and asks the reasoning model for a
   single structured response.
3. Parses the response with :func:`parse_dreaming_output`.
4. Writes each :class:`ConsolidatedMemory` into the ``memories``
   table with ``source="dreaming"`` and ``provenance_job_id``
   pointing back at the job row, so every dreaming-derived memory
   can be traced to the pass that produced it.
5. Updates the job row with the output counts, the session summary,
   and the terminal status (``completed`` / ``failed``).

The LLM call is dependency-injected via the ``dream_fn`` argument
so tests run without a live provider. The default implementation
(``_default_dream_fn``) shells out to the configured dreaming model
via litellm — same dependency the LCM compaction summariser uses.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dreaming.prompt import DREAMING_PROMPT
from app.core.dreaming.schema import (
    DreamingOutput,
    parse_dreaming_output,
)
from app.crud.memory import find_similar_memories, insert_memory
from app.db import async_session_maker
from app.models import ChatMessage, Conversation, DreamingJob

logger = logging.getLogger(__name__)


# Window sizes for the two scopes. Tuned so a single pass fits in
# a 32k-token context window even with verbose tool turns.
_SESSION_END_MESSAGE_LIMIT = 50
_DAILY_ROLLUP_HOURS = 24
_DAILY_ROLLUP_MESSAGE_LIMIT = 200

# Per-input token cap so a runaway message thread can't blow the
# prompt budget. Tokens are estimated as roughly 4 chars / token,
# which is the same approximation LCM uses for its leaf chunks.
_CHARS_PER_TOKEN = 4
_MAX_INPUT_CHARS = 24_000 * _CHARS_PER_TOKEN

DreamFn = Callable[[str], Awaitable[str]]
"""Signature for the dreaming-prompt LLM call.

Takes the rendered prompt; returns the model's raw string output.
Injectable so tests can swap in a deterministic stub instead of a
network round-trip.
"""


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
"""Factory shape callers can swap in to redirect the runner to a test DB.

Defaults to :data:`app.db.async_session_maker` — pytest fixtures
that need to assert against in-memory state pass their own
sessionmaker so the runner reads/writes through the same engine
as the test's setup.
"""


async def run_dreaming_job(
    job_id: uuid.UUID,
    *,
    dream_fn: DreamFn | None = None,
    session_factory: SessionFactory | None = None,
) -> None:
    """Drive one dreaming pass from ``pending`` to ``completed`` or ``failed``.

    Idempotent on the ``status`` column: if the job has already run
    (``status != "pending"``) the function short-circuits without
    touching the row. Callers can safely retry on transient errors
    by clearing ``error_text`` + setting ``status="pending"`` before
    invoking this again.

    Args:
        job_id: Primary key of the :class:`DreamingJob` to run.
        dream_fn: Optional override for the LLM call seam — lets
            tests inject a deterministic response without a provider.
            When ``None``, the default impl uses litellm via
            :func:`_default_dream_fn`.
        session_factory: Optional override for the session maker.
            Defaults to :data:`async_session_maker`; tests pass
            their own factory so the runner reads/writes through
            the same in-memory SQLite engine as the test setup.
    """
    effective_fn = dream_fn or _default_dream_fn
    factory = session_factory or async_session_maker
    async with factory() as session:
        job = await _claim_pending_job(session, job_id)
        if job is None:
            return
        try:
            input_text = await _build_input_window(session, job)
            raw_response = await effective_fn(_render_prompt(input_text))
            parsed = parse_dreaming_output(raw_response)
            memories_written = await _persist_outputs(session, job, parsed)
            await _mark_completed(
                session,
                job,
                parsed,
                memories_written=memories_written,
                input_chars=len(input_text),
                raw_chars=len(raw_response),
            )
        except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
            logger.exception("DREAMING_RUN_ERR job_id=%s", job_id)
            await _mark_failed(session, job, error=str(exc))


async def _claim_pending_job(session: AsyncSession, job_id: uuid.UUID) -> DreamingJob | None:
    """Flip ``pending`` → ``running`` + set ``started_at``; return ``None`` otherwise."""
    job = await session.get(DreamingJob, job_id)
    if job is None:
        logger.warning("DREAMING_JOB_MISSING job_id=%s", job_id)
        return None
    if job.status != "pending":
        logger.info(
            "DREAMING_JOB_SKIP_NONPENDING job_id=%s status=%s",
            job_id,
            job.status,
        )
        return None
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(job)
    return job


async def _build_input_window(session: AsyncSession, job: DreamingJob) -> str:
    """Pull the messages the dreaming pass should reflect on."""
    if job.scope == "session_end" and job.conversation_id is not None:
        rows = await _last_n_messages_in_conversation(
            session,
            conversation_id=job.conversation_id,
            limit=_SESSION_END_MESSAGE_LIMIT,
        )
    else:
        rows = await _last_24h_messages_for_user(
            session,
            user_id=job.user_id,
            limit=_DAILY_ROLLUP_MESSAGE_LIMIT,
        )
    return _format_input(rows)


async def _last_n_messages_in_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    limit: int,
) -> list[ChatMessage]:
    """Return the most recent ``limit`` messages in ``conversation_id``, oldest first."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(desc(ChatMessage.ordinal))
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def _last_24h_messages_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
) -> list[ChatMessage]:
    """Return ``user_id``'s messages from the last 24h, oldest first."""
    cutoff = datetime.now(UTC) - timedelta(hours=_DAILY_ROLLUP_HOURS)
    stmt = (
        select(ChatMessage)
        .join(Conversation, Conversation.id == ChatMessage.conversation_id)
        .where(Conversation.user_id == user_id)
        .where(ChatMessage.created_at >= cutoff)
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


def _format_input(rows: list[ChatMessage]) -> str:
    """Render messages as a plain transcript, capped at ``_MAX_INPUT_CHARS``.

    Plain text keeps the dreaming prompt token-efficient — tool
    metadata + provider-specific block types from the live history
    don't help the reflection pass. We tag each line with the role
    so the model can tell user input apart from assistant output.
    """
    lines: list[str] = []
    total = 0
    for row in rows:
        line = f"[{row.role}] {row.content or ''}"
        if total + len(line) > _MAX_INPUT_CHARS:
            lines.append("[truncated: input window exceeded]")
            break
        lines.append(line)
        total += len(line) + 1  # +1 for the newline
    return "\n".join(lines)


def _render_prompt(input_text: str) -> str:
    """Combine the static dreaming prompt and the chat transcript window."""
    return f"{DREAMING_PROMPT}\n\n# Recent activity\n\n{input_text}"


async def _persist_outputs(
    session: AsyncSession,
    job: DreamingJob,
    parsed: DreamingOutput,
) -> int:
    """Write each consolidated memory; return the count actually written.

    Dedupe pre-check: for each candidate memory we run
    :func:`find_similar_memories` first and skip when the substring
    match returns anything — the model often re-states the same
    fact across runs and we don't want a memory list that doubles
    every night.
    """
    written = 0
    for entry in parsed.consolidated_memories:
        existing = await find_similar_memories(
            session,
            job.user_id,
            text=entry.text,
            kind=entry.kind,
        )
        if existing:
            continue
        await insert_memory(
            session,
            job.user_id,
            kind=entry.kind,
            text=entry.text,
            source="dreaming",
            workspace_id=job.workspace_id,
            conversation_id=job.conversation_id,
            provenance_job_id=job.id,
        )
        written += 1
    return written


async def _mark_completed(
    session: AsyncSession,
    job: DreamingJob,
    parsed: DreamingOutput,
    *,
    memories_written: int,
    input_chars: int,
    raw_chars: int,
) -> None:
    """Stamp the job row with the run's results and publish the completion event."""
    job.status = "completed"
    job.completed_at = datetime.now(UTC)
    job.memories_written = memories_written
    job.patterns_written = len(parsed.patterns)
    job.followups_written = len(parsed.followups)
    job.session_summary = parsed.session_summary or None
    # Char-based estimate matches the LCM convention; the dedicated
    # tokeniser comes online when the provider seam stabilises.
    job.input_token_count = input_chars // _CHARS_PER_TOKEN
    job.output_token_count = raw_chars // _CHARS_PER_TOKEN
    await session.commit()
    await _publish_completion(job)


async def _mark_failed(session: AsyncSession, job: DreamingJob, *, error: str) -> None:
    """Stamp the job row as failed with a truncated error message."""
    job.status = "failed"
    job.completed_at = datetime.now(UTC)
    job.error_text = error[:1000]
    await session.commit()
    await _publish_completion(job)


async def _publish_completion(job: DreamingJob) -> None:
    """Publish a :class:`DreamingCompletedEvent` for downstream subscribers.

    Lazy imports keep the event-bus dependency outside the
    runner's hot path — important because the runner runs in
    background tasks where a top-level import would force every
    deployment to pay the bus's startup cost regardless of whether
    dreaming is enabled.
    """
    from app.core.event_bus import (  # noqa: PLC0415
        DreamingCompletedEvent,
        publish_if_available,
    )

    await publish_if_available(
        DreamingCompletedEvent(
            job_id=job.id,
            user_id=job.user_id,
            conversation_id=job.conversation_id,
            scope=job.scope,
            status=job.status,
            memories_written=job.memories_written,
            patterns_written=job.patterns_written,
            followups_written=job.followups_written,
            session_summary=job.session_summary,
        )
    )


async def _default_dream_fn(prompt: str) -> str:
    """Default dreaming-call implementation — lazy litellm wrapper.

    Kept narrow on purpose: a dreaming pass is a one-shot text
    completion, not a streaming agent loop, so going through the
    full provider seam would be overkill. ``litellm.acompletion``
    is the same dependency the LCM summariser uses, so we inherit
    its provider routing for free.
    """
    # ``litellm`` is a hard dep of the gateway; lazy import keeps the
    # module load cost low when the dreaming runner is never invoked.
    import litellm  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    response = await litellm.acompletion(
        model=settings.dreaming_model_id,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return str(response.choices[0].message.content or "")


__all__ = [
    "DreamFn",
    "run_dreaming_job",
]
