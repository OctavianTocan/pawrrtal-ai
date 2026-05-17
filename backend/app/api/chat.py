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

from app.api._chat_cost_budget import enforce_cost_budget
from app.api._chat_events import publish_turn_started
from app.api._chat_permissions import build_chat_permission_check
from app.channels import resolve_channel, surface_from_header
from app.channels.base import ChannelMessage
from app.channels.turn_runner import ChatTurnInput, EventHook, run_turn
from app.core.agent_tools import build_agent_tools
from app.core.providers import StreamEvent, default_model, resolve_llm
from app.core.request_logging import get_request_id
from app.core.tools.artifact_agent import (
    ARTIFACT_TOOL_NAME,
    ArtifactValidationError,
    build_artifact,
)
from app.crud.conversation import (
    get_conversation,
    update_conversation_model,
)
from app.crud.workspace import get_default_workspace
from app.db import User, get_async_session
from app.schemas import ChatRequest
from app.users import get_allowed_user

logger = logging.getLogger(__name__)

# How many recent messages to send as context to the provider.
# Keeps token usage predictable while preserving recent turns.
_HISTORY_WINDOW = 20


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


async def _require_workspace_root(
    *,
    user_id: uuid.UUID,
    session: AsyncSession,
    request_id: str,
) -> Path:
    """Return the user's default workspace path or reject the chat turn."""
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
        logger.error("CHAT_WORKSPACE_MISSING rid=%s user_id=%s path=%s", request_id, user_id, root)
        raise HTTPException(
            status_code=412,
            detail="Workspace directory is missing on disk.  Re-run onboarding.",
        )
    return root


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
        x_nexus_surface: str | None = Header(default=None),
    ) -> StreamingResponse:
        """Stream an AI response as Server-Sent Events.

        SSE event shapes:
          {"type": "delta", "content": "..."}      — text chunk
          {"type": "thinking", "content": "..."}   — reasoning (when available)
          {"type": "tool_use", "name": "...", "input": {...}}
          {"type": "tool_result", "content": "..."}
          {"type": "error", "content": "..."}      — stream-level error
          [DONE]

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
        surface = surface_from_header(x_nexus_surface)
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

        # Resolve model: request overrides stored model, stored model overrides
        # catalog default.  Request and stored values are already canonical
        # (validated by Pydantic at the API boundary); ``default_model().id``
        # is the canonical wire form of the catalog default.
        model_id = request.model_id or conversation.model_id or default_model().id

        # Persist model change if it differs from what is stored
        if model_id != conversation.model_id:
            await update_conversation_model(
                model_id=model_id,
                user_id=user.id,
                conversation_id=request.conversation_id,
                session=session,
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
        root = await _require_workspace_root(user_id=user.id, session=session, request_id=rid)

        provider = resolve_llm(model_id, user_id=user.id, workspace_root=root)
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

        # Per-turn tool composition lives in `app.core.agent_tools` —
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

        agent_tools = build_agent_tools(
            workspace_root=root,
            user_id=user.id,
            send_fn=_web_send_fn,
            surface=surface,
            conversation_id=request.conversation_id,
            model_id=model_id,
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
        # Build the per-request permission gate (PR 03b + PR 06).  The
        # helper bundles workspace-context loading, ``PermissionContext``
        # construction, and the cross-provider closure that adapts
        # ``(tool_name, arguments)`` so the context never leaks into the
        # agent loop. Both providers consume the same closure — Claude
        # via the SDK's ``can_use_tool`` hook, Gemini via
        # ``AgentLoopConfig.permission_check``.
        permission_check_for_request = build_chat_permission_check(
            user_id=user.id,
            workspace_root=root,
            conversation_id=request.conversation_id,
            surface=surface,
        )

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
        turn_input = ChatTurnInput(
            conversation_id=request.conversation_id,
            user_id=user.id,
            question=request.question,
            provider=provider,
            channel=channel,
            channel_message=channel_message,
            db_session=session,
            workspace_root=root,
            tools=agent_tools,
            reasoning_effort=request.reasoning_effort,
            permission_check=permission_check_for_request,
            images=image_inputs,
            history_window=_HISTORY_WINDOW,
            log_tag="CHAT",
            log_extras={
                "rid": rid,
                "model_id": model_id,
                "surface": surface,
            },
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
