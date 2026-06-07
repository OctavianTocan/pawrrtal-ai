"""Regression: chat router must NOT pass the request-scoped session into the stream.

When the chat router forwards ``Depends(get_async_session)``'s session into
``ChatTurnInput.db_session``, the streaming generator (``run_turn`` → ``_turn_session``
fallback short-circuit) holds the request session past the lifetime of the route
handler. Under SQLite/aiosqlite, by the time ``_finalize_turn`` runs, the underlying
aiosqlite connection has been torn down and any ``session.execute`` raises
``sqlite3.OperationalError: no active connection`` — leaving the assistant message
row stuck in ``status="streaming"`` forever. Postgres masks this because the pool
can transparently reconnect via ``pool_pre_ping``; aiosqlite does not.

The fix: the chat router leaves ``db_session`` at its ``None`` default so the
turn runner opens its own ``async_session_maker()`` session inside the streaming
generator — same connection lifecycle the Telegram path already uses.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.channels.sse import SSEChannel
from app.models import Workspace
from app.providers.base import StreamEvent
from app.providers.catalog import first_catalog_model


class _FakeProvider:
    """Yields one trivial delta so the stream runs to completion without an LLM."""

    async def stream(
        self,
        question: str,
        conversation_id: object,
        user_id: object,
        history: object = None,
        tools: object = None,
        system_prompt: object = None,
        reasoning_effort: object = None,
        images: object = None,
    ) -> AsyncIterator[dict[str, str]]:
        """Emit one text delta so ``_finalize_turn`` has something to persist."""
        yield {"type": "delta", "content": "ok"}


@pytest.mark.anyio
async def test_chat_router_does_not_pass_request_session_into_turn_input(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """Chat router must leave ``ChatTurnInput.db_session`` at its ``None`` default.

    Capturing the kwargs the router uses to build ``ChatTurnInput`` is the
    cheapest way to lock in the SQLite-safe lifecycle: if a future refactor
    re-introduces ``db_session=session``, the streaming generator holds the
    request session past the route handler and aiosqlite fails. See the
    module docstring for the full failure mode.
    """
    conversation_id = uuid4()
    await client.post(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "SQLite Lifecycle"},
    )
    monkeypatch.setattr(
        "app.chat.router.resolve_llm",
        lambda _model_id, **kwargs: _FakeProvider(),
    )

    captured: dict[str, Any] = {}

    # The chat router imports ``ChatTurnInput`` from ``app.channels.turn_orchestrator``.
    # Patch the symbol the router actually resolves so we observe the real
    # construction call, not a stand-in.
    from app.channels.turn_orchestrator import ChatTurnInput as _OriginalChatTurnInput

    def _capturing_chat_turn_input(**kwargs: Any) -> _OriginalChatTurnInput:
        """Capture kwargs then delegate to the real dataclass constructor."""
        captured.update(kwargs)
        return _OriginalChatTurnInput(**kwargs)

    monkeypatch.setattr("app.chat.router.ChatTurnInput", _capturing_chat_turn_input)

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hello",
            "conversation_id": str(conversation_id),
            "model_id": first_catalog_model().id,
        },
    )

    assert response.status_code == 200, response.text
    # ``db_session`` may be absent entirely (preferred) or explicitly ``None``.
    # Either is safe; passing the request session is the bug.
    assert captured.get("db_session") is None, (
        f"Chat router must not pass the request session into ChatTurnInput; "
        f"got db_session={captured.get('db_session')!r}. See pawrrtal-0dgj — "
        "passing the request session breaks SQLite/aiosqlite chat persistence."
    )


@pytest.mark.anyio
async def test_chat_finalizes_assistant_status_on_sqlite(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """End-to-end: assistant message row reaches ``status="complete"`` on SQLite.

    Before the fix, ``_finalize_turn`` ran on a dead aiosqlite connection and
    silently swallowed the resulting ``OperationalError`` — leaving the
    assistant placeholder stuck in ``status="streaming"``. This is the exact
    failing check (``assistant_status_complete: status=streaming``) the
    ``paw verify chat-roundtrip`` scenario reports.
    """
    conversation_id = uuid4()
    await client.post(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Finalize"},
    )
    monkeypatch.setattr(
        "app.chat.router.resolve_llm",
        lambda _model_id, **kwargs: _FakeProvider(),
    )

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hi",
            "conversation_id": str(conversation_id),
            "model_id": first_catalog_model().id,
        },
    )
    assert response.status_code == 200
    assert "data: [DONE]" in response.text

    messages_resp = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert messages_resp.status_code == 200
    messages = messages_resp.json()
    assistant_rows = [m for m in messages if m["role"] == "assistant"]
    assert assistant_rows, "expected at least one assistant message row"
    final = assistant_rows[-1]
    assert final.get("assistant_status") == "complete", (
        f"assistant row must finalize to status=complete on SQLite; "
        f"got {final.get('assistant_status')!r}. The streaming generator's "
        "persistence path must not depend on the request session."
    )


@pytest.mark.anyio
async def test_sse_done_frame_waits_for_turn_finalization() -> None:
    """SSE must not emit ``[DONE]`` before the assistant row is finalized.

    Real CLI/browser clients commonly stop reading when they see the terminal
    SSE frame. If the channel emits ``[DONE]`` before ``_finalize_turn`` runs,
    an immediate messages refetch can observe the assistant row as still
    ``streaming`` even though the visible response completed.
    """
    from app.channels.turn_orchestrator import _finalizing_stream

    finalized = False

    async def _source() -> AsyncIterator[StreamEvent]:
        yield {"type": "delta", "content": "ok"}

    async def _finalize() -> None:
        nonlocal finalized
        finalized = True

    channel = SSEChannel()
    async for chunk in channel.deliver(
        _finalizing_stream(_source(), _finalize),
        message=cast(Any, {}),
    ):
        if chunk == b"data: [DONE]\n\n":
            assert finalized


@pytest.mark.anyio
async def test_finalize_turn_leaves_message_complete_on_cost_write_failure(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_default_workspace: Workspace,
) -> None:
    """Cost-ledger failure must NOT strand the assistant row at ``status="streaming"``.

    ``_finalize_turn`` splits its writes into two transactions: the
    assistant-row finalize (hard requirement) and the cost-ledger insert
    (best-effort observability). A failure in the cost write must be
    swallowed at the broad ``SQLAlchemyError`` boundary — narrower
    ``OperationalError`` / ``IntegrityError`` excepts would let
    ``PendingRollbackError`` / ``InvalidRequestError`` propagate into the
    streaming generator after the SSE body has yielded, breaking the
    response *and* leaving the assistant row stuck mid-stream.

    Inject a synthetic ``IntegrityError`` into the cost-write path and
    assert the assistant row still reaches ``status="complete"``.
    """
    from sqlalchemy.exc import IntegrityError

    conversation_id = uuid4()
    await client.post(
        f"/api/v1/conversations/{conversation_id}",
        json={"title": "Cost Failure"},
    )
    monkeypatch.setattr(
        "app.chat.router.resolve_llm",
        lambda _model_id, **kwargs: _FakeProvider(),
    )

    async def _explode(**_kwargs: Any) -> None:
        """Synthetic cost-write failure that should be swallowed."""
        raise IntegrityError("synthetic", params=None, orig=Exception("boom"))

    # Patch where the symbol is looked up — ``turn_orchestrator`` imported it
    # at module load, so patching ``app.channels._turn_cost`` would miss
    # the in-scope reference.
    monkeypatch.setattr(
        "app.channels.turn_orchestrator.finalize.record_turn_cost_if_enabled",
        _explode,
    )

    response = await client.post(
        "/api/v1/chat/",
        json={
            "question": "hi",
            "conversation_id": str(conversation_id),
            "model_id": first_catalog_model().id,
        },
    )
    assert response.status_code == 200
    assert "data: [DONE]" in response.text

    messages_resp = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert messages_resp.status_code == 200
    messages = messages_resp.json()
    assistant_rows = [m for m in messages if m["role"] == "assistant"]
    assert assistant_rows, "expected at least one assistant message row"
    final = assistant_rows[-1]
    assert final.get("assistant_status") == "complete", (
        f"assistant row must reach status=complete even when the cost-ledger "
        f"write raises; got {final.get('assistant_status')!r}. The broadened "
        "SQLAlchemyError catch in _finalize_turn is the headline guarantee of "
        "the split-transaction design."
    )
