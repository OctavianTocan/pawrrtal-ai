"""Chat API — channel-routed, provider-agnostic streaming endpoint."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import anyio
from fastapi import Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter
from opentelemetry import trace as _otel_trace
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.hooks import build_pre_turn_hooks
from app.agents.tools import build_agent_tools

# ``ChannelMessage`` is re-exported by ``app.channels.__init__``; we
# pull all three names from the same package to keep chat.py's
# fan-out under sentrux's ``no_god_files`` budget.
from app.channels import ChannelMessage, resolve_channel, surface_from_header
from app.channels.turn_runner import ChatTurnInput, EventHook, load_agy_conversation_id, run_turn
from app.chat import (
    enforce_cost_budget,
    load_external_mcp_configs,
    publish_turn_started,
)
from app.conversations.crud import (
    apply_model_switch_and_normalize_reasoning,
    get_conversation,
)
from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.infrastructure.middleware.logging import get_request_id
from app.providers import StreamEvent, resolve_llm
from app.schemas import ChatRequest
from app.tools.artifact_agent import (
    ARTIFACT_TOOL_NAME,
    ArtifactValidationError,
    build_artifact,
)
from app.workspace.crud import get_default_workspace

logger = logging.getLogger(__name__)

# How many recent messages to send as context to the provider.
# Keeps token usage predictable while preserving recent turns.
_HISTORY_WINDOW = 20


# TODO: This should probably not be here. This file is about the chat API, not observability.
def _annotate_chat_span(
    *,
    user_id: object,
    conversation_id: object,
    model_id: str | None,
    surface: str,
    question_len: int,
    request_id: str,
) -> None:
    """Attach pawrrtal-namespaced attributes to the active OTel span.

    Pure observability — a failure here must never break the chat
    path, so the whole body is wrapped in a broad ``try / except``.
    ``get_current_span()`` returns a no-op when telemetry is disabled.
    """
    try:
        span = _otel_trace.get_current_span()
        span.set_attribute("pawrrtal.user_id", str(user_id))
        span.set_attribute("pawrrtal.conversation_id", str(conversation_id))
        span.set_attribute("pawrrtal.model_id", model_id or "<default>")
        span.set_attribute("pawrrtal.surface", surface)
        span.set_attribute("pawrrtal.question_len", question_len)
        span.set_attribute("pawrrtal.request_id", request_id)
    except Exception:
        logger.debug("OTEL_SPAN_ANNOTATE_FAILED", exc_info=True)


# TODO: This should probably not be here. This file is about the chat API, not tool artifacts.
def _maybe_artifact_event(event: StreamEvent) -> StreamEvent | None:
    """Build an ``artifact`` SSE event from a ``render_artifact`` tool_use.

    Returns ``None`` for any other event so the caller can no-op cheaply.
    Validation errors are swallowed silently here — the tool's own
    ``execute`` callback will return a corrective error string to the LLM
    so the agent can self-correct on the next turn, and emitting a half-
    formed artifact event would leave the frontend rendering nothing.
    """
    if event.get("type") != "tool_use" or event.get("name") != ARTIFACT_TOOL_NAME:
        return None
    tool_input = event.get("input") or {}
    title = tool_input.get("title")
    spec = tool_input.get("spec")
    if not isinstance(title, str) or not isinstance(spec, dict):
        return None
    try:
        payload = build_artifact(title=title, spec=spec)
    except ArtifactValidationError:
        return None
    return StreamEvent(
        type="artifact",
        artifact={
            "id": payload["id"],
            "title": payload["title"],
            "spec": payload["spec"],
            # Echo the originating tool_use_id so the frontend can attach
            # this artifact to the matching tool-call slot if it wants to.
            "tool_use_id": event.get("tool_use_id", ""),
        },
    )


async def _require_workspace(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    request_id: str,
) -> tuple[uuid.UUID, Path]:
    """Return the user's default workspace ``(id, path)`` or reject the chat turn.

    Returns the workspace UUID alongside the directory path so callers
    can pass both into :func:`app.agents.tools.build_agent_tools` —
    the UUID drives plugin activation (and, post-migration, env-key
    resolution); the path drives the existing core workspace tools.
    """
    workspace = await get_default_workspace(user_id, session)
    if workspace is None:
        raise HTTPException(
            status_code=412,
            detail="Onboarding not completed: no default workspace exists for this user.",
        )
    root = Path(workspace.path)
    # Blocking ``Path.exists()`` would stall the event loop on slow
    # FS / network mounts — route through ``anyio.Path`` so the stat
    # runs in a worker thread.
    if not await anyio.Path(root).exists():
        # Workspace row exists but the directory is gone (manually
        # deleted, volume wipe, etc.).  Same outcome — do not run.
        logger.error(
            "CHAT_WORKSPACE_MISSING rid=%s user_id=%s path=%s",
            request_id,
            user_id,
            root,
        )
        raise HTTPException(
            status_code=412,
            detail="Workspace directory is missing on disk.  Re-run onboarding.",
        )
    return workspace.id, root


def get_chat_router() -> APIRouter:
    """Build the chat ``APIRouter`` mounted at ``/api/v1/chat``.

    Returns:
        An ``APIRouter`` exposing a single streaming ``POST /`` endpoint
        that emits Server-Sent Events from the resolved AI provider.
    """
    router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

    @router.post("/")
    async def chat(
        request: ChatRequest,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
        x_pawrrtal_surface: str | None = Header(default=None),
    ) -> StreamingResponse:
        """Stream an AI response as Server-Sent Events.

        SSE event shapes (emitted by providers, the agent loop, and this
        router):

          {"type": "delta", "content": "..."}
              Provider-emitted text chunk (every provider).
          {"type": "thinking", "content": "...", "block_index": N?}
              Provider-emitted reasoning chunk; ``block_index`` marks
              paragraph boundaries for renderers that group blocks.
          {"type": "tool_use", "name": "...", "input": {...},
           "tool_use_id": "...", "display": {...}?}
              Provider-emitted tool call.
          {"type": "tool_result", "content": "...", "tool_use_id": "...",
           "is_error": bool?}
              Provider-emitted tool result.
          {"type": "usage", "input_tokens": N, "output_tokens": N,
           "cost_usd": F}
              Provider-emitted per-turn token/cost accounting. Powers the
              cost ledger; consumers can ignore.
          {"type": "artifact",
           "artifact": {"id": "...", "title": "...", "spec": {...},
                        "tool_use_id": "..."}}
              Emitted by ``_maybe_artifact_event`` in this router when the
              agent calls ``render_artifact``. Renderers render this as a
              first-class artifact card.
          {"type": "message", "content": "...", "attachment": "path"?,
           "mime": "..."?}
              Emitted by this router's ``send_fn`` for the agent's
              mid-turn ``send_message`` tool (text + optional file).
          {"type": "agent_terminated", "content": "..."}
              Emitted by the agent loop when a safety cap fires
              (iteration cap, wall-clock budget, consecutive-error
              threshold). The loop already wrote ``[DONE]`` after this
              event; renderers should treat it as a controlled stop with
              an explanation, not as a stream error.
          {"type": "error", "content": "...", "error_code": "..."?}
              Stream-level error (provider failure, exception during the
              agent loop). The transport raises after this; no further
              frames follow.
          [DONE]
              Terminal sentinel — the stream ends after this line.

        While streaming, the endpoint also persists the turn to the
        ``chat_messages`` table — the user prompt as a row, the assistant
        reply as a placeholder that is patched on stream end with the full
        chain-of-thought state. This is what powers ``GET /conversations/:id/messages``
        rehydration: the chat UI reads from ``chat_messages``, not from
        provider-native transcript logs.

        The provider is resolved from model_id — the endpoint is fully
        provider-agnostic. Changing model_id changes the provider; the
        stream format never changes.
        """
        # Entry log — pairs with REQ_IN/REQ_OUT from the request middleware via rid.
        # Question length, not contents, to avoid leaking PII into the log file.
        surface = surface_from_header(x_pawrrtal_surface)
        channel = resolve_channel(surface)

        rid = get_request_id()

        # Annotate the FastAPI-instrumentor span with semantic attributes
        # so a trace search by user / conversation / model / surface lands
        # the right request immediately.
        _annotate_chat_span(
            user_id=user.id,
            conversation_id=request.conversation_id,
            model_id=request.model_id,
            surface=surface,
            question_len=len(request.question),
            request_id=rid,
        )
        logger.info(
            "CHAT_IN  rid=%s user_id=%s conversation_id=%s model_id=%s surface=%s question_len=%d",
            rid,
            user.id,
            request.conversation_id,
            request.model_id or "<default>",
            surface,
            len(request.question),
        )

        conversation = await get_conversation(user.id, session, request.conversation_id)
        if conversation is None:
            logger.warning(
                "CHAT_404 rid=%s user_id=%s conversation_id=%s",
                rid,
                user.id,
                request.conversation_id,
            )
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Resolve model: the request overrides the conversation's stored
        # model. Both are already canonical (validated by Pydantic at the API
        # boundary). There is no default fallback — a model must be supplied
        # by the request or already pinned on the conversation.
        model_id = request.model_id or conversation.model_id
        if not model_id:
            raise HTTPException(
                status_code=422,
                detail="model_id is required: no model on the request or the conversation",
            )

        # Apply the model switch (if any) and re-normalize the stored
        # reasoning_effort against the current model in a *single*
        # transaction (#366). Previously this was two consecutive
        # ``session.commit`` calls — a crash between them left the row
        # with a fresh ``model_id`` but a stale ``reasoning_effort``
        # belonging to the previous model. Catalog validation lives in
        # ``resolve_reasoning_effort``, the same helper used by the
        # Telegram /thinking picker and /model command.
        (
            reasoning_resolution,
            _previous_reasoning_effort,
        ) = await apply_model_switch_and_normalize_reasoning(
            conversation=conversation,
            new_model_id=model_id,
            session=session,
        )
        effective_reasoning_effort = (
            request.reasoning_effort
            if request.reasoning_effort is not None
            else reasoning_resolution.effective
        )

        # Resolve the user's default workspace.  A workspace is created as
        # part of onboarding, so its absence means the user hasn't finished
        # that flow yet — the agent should not run at all in that state.
        # Refuse with 412 (Precondition Failed) so the frontend can route to
        # onboarding instead of pretending we shipped a degraded reply.
        #
        # Hoisted above ``resolve_llm`` so we can pass ``workspace_root``
        # into the Claude SDK as its ``cwd``. Without it, the SDK falls
        # back to the uvicorn process directory and writes its transcript
        # files there.
        workspace_id, root = await _require_workspace(
            user_id=user.id, session=session, request_id=rid
        )
        # Pre-flight per-user cost gate (PR 04).  Refuses with HTTP
        # 402 when the user's rolling-window spend + a small reservation
        # would exceed ``cost_max_per_user_daily_usd``.  This sits
        # *after* the workspace gate (so an onboarding-incomplete user
        # never sees a confusing 402) and *before* tool composition /
        # provider resolution (so a denied request is cheap).  The
        # Claude SDK enforces the per-request cap natively via
        # ``max_budget_usd``; this gate enforces the per-user cap.
        await enforce_cost_budget(
            user_id=user.id,
            session=session,
            rid=rid,
        )

        # Provider construction must happen *after* workspace resolution so
        # workspace-scoped API-key overrides (Gemini/Claude) take effect.
        # ``workspace_root`` is also forwarded so the Claude SDK subprocess
        # writes its transcripts under the user's workspace rather than
        # the uvicorn process directory.
        provider = resolve_llm(model_id, workspace_root=root)
        # Per-turn tool composition lives in `app.agents.tools` —
        # the chat router only decides *that* the agent gets tools,
        # not *which* (that's the builder's job, and where future
        # per-agent / per-user permission gating will land).  Provider
        # files stay tool-agnostic; see
        # `.claude/rules/architecture/no-tools-in-providers.md`.
        # Web send_fn — lets the agent call send_message() to push text or
        # files back to the user mid-turn.  Events are placed on a per-request
        # queue and drained into the SSE stream after each provider event,
        # keeping chat.py free of any tool-name coupling.
        _web_send_queue: asyncio.Queue[StreamEvent] = asyncio.Queue()

        async def _web_send_fn(
            text: str | None,
            file_path: Path | None,
            mime: str | None,
        ) -> None:
            event: StreamEvent = {"type": "message", "content": text or ""}
            if file_path is not None:
                event["attachment"] = str(file_path.relative_to(root))
                event["mime"] = mime
            await _web_send_queue.put(event)

        external_mcp_configs = await load_external_mcp_configs(session=session, user_id=user.id)
        agent_tools = build_agent_tools(
            workspace_root=root,
            user_id=user.id,
            workspace_id=workspace_id,
            send_fn=_web_send_fn,
            surface=surface,
            conversation_id=request.conversation_id,
            model_id=model_id,
            external_mcp_configs=external_mcp_configs,
        )

        def _artifact_hook(event: StreamEvent) -> list[StreamEvent]:
            extra = _maybe_artifact_event(event)
            return [extra] if extra is not None else []

        def _drain_send_queue(_event: StreamEvent) -> list[StreamEvent]:
            out: list[StreamEvent] = []
            while not _web_send_queue.empty():
                out.append(_web_send_queue.get_nowait())
            return out

        channel_message: ChannelMessage = {
            "user_id": user.id,
            "conversation_id": request.conversation_id,
            "text": request.question,
            "surface": surface,
            "model_id": model_id,
            "metadata": {},
        }
        # PR 09: forward multimodal image inputs from the request body to
        # the provider via ChatTurnInput.images.  Each provider bridges
        # these into its native content-block shape — Claude as
        # messages.content image blocks (PR 05), Gemini as
        # Part.from_bytes.
        image_inputs = (
            [{"data": img.data, "media_type": img.media_type} for img in request.images]
            if request.images
            else None
        )

        # Ensure native Codex threads are created before the first streamed turn.
        # Non-Codex providers return None and keep the existing history path.
        from app.providers.openai_codex.threads import ensure_codex_thread_state  # noqa: PLC0415

        codex_thread_state = await ensure_codex_thread_state(
            conversation_id=request.conversation_id,
            provider=provider,
            workspace_root=root,
            model_id=model_id,
            tools=agent_tools,
            reasoning_effort=effective_reasoning_effort,
            question=request.question,
        )
        agy_conversation_id = await load_agy_conversation_id(request.conversation_id)

        # ``db_session`` is intentionally left at its ``None`` default so the
        # turn runner opens its own ``async_session_maker()`` session inside
        # the streaming generator. Passing the request-scoped session from
        # ``Depends(get_async_session)`` breaks under SQLite/aiosqlite because
        # ``StreamingResponse`` keeps the response body iterating long after
        # the route handler returns — by the time ``_finalize_turn`` runs,
        # aiosqlite's underlying connection has been torn down and any
        # ``session.execute`` raises ``OperationalError: no active connection``.
        # Postgres masks this because pool checkout + ``pool_pre_ping`` can
        # transparently reconnect; aiosqlite does not. Issue: pawrrtal-0dgj.
        turn_input = ChatTurnInput(
            conversation_id=request.conversation_id,
            user_id=user.id,
            question=request.question,
            provider=provider,
            channel=channel,
            channel_message=channel_message,
            workspace_root=root,
            tools=agent_tools,
            # ``effective_reasoning_effort`` is the resolved value
            # from the shared backstop: per-turn override wins,
            # otherwise the conversation's normalized stored effort.
            reasoning_effort=effective_reasoning_effort,
            images=image_inputs,
            history_window=_HISTORY_WINDOW,
            log_tag="CHAT",
            log_extras={
                "rid": rid,
                "model_id": model_id,
                "surface": surface,
            },
            pre_turn_hooks=build_pre_turn_hooks(),
            codex_thread_id=codex_thread_state.thread_id,
            codex_thread_prompt_hash=codex_thread_state.prompt_hash,
            codex_lightweight_prompt=codex_thread_state.lightweight_prompt,
            agy_conversation_id=agy_conversation_id,
        )
        hooks: list[EventHook] = [_artifact_hook, _drain_send_queue]

        # PR 10: announce the turn so subscribers (audit, metrics,
        # webhook delivery) can react.  Fire-and-forget via the global
        # bus accessor; no-op when the bus is unset.
        await publish_turn_started(
            user_id=user.id,
            conversation_id=request.conversation_id,
            surface=surface,
            model_id=model_id,
        )

        async def event_stream() -> AsyncGenerator[bytes]:
            """Yield channel-encoded bytes from the shared turn runner."""
            async for chunk in run_turn(turn_input, event_hooks=hooks):
                yield chunk

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router
