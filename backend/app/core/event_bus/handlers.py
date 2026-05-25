"""Event-bus subscribers — AgentHandler + NotificationService.

Wires PRs 10/11/12 end-to-end:

* :class:`AgentHandler` subscribes to :class:`WebhookEvent` and
  :class:`ScheduledEvent`, runs an agent turn against the payload,
  and publishes :class:`AgentResponseEvent` carrying the assistant's
  reply text.
* :class:`NotificationService` subscribes to
  :class:`AgentResponseEvent` and delivers each one to the
  configured Telegram chats (or the default broadcast list when
  no specific chat was requested).

Both are constructed once per process and registered on the global
:class:`EventBus` from the FastAPI lifespan (``main.py``).  Failures
in either handler are isolated by the bus's
``return_exceptions=True`` dispatch — a crashed delivery never
breaks an agent turn or a sibling handler.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core.event_bus.bus import Event
from app.core.event_bus.types import (
    AgentResponseEvent,
    ScheduledEvent,
    WebhookEvent,
)
from app.core.providers import default_model, resolve_llm
from app.db import async_session_maker

logger = logging.getLogger(__name__)

# How many characters of the webhook payload to flatten into the prompt.
# Past this we truncate so a noisy GitHub payload can't blow the model
# context in one go.
_PAYLOAD_PROMPT_BUDGET_CHARS = 2000

# Per-message Telegram cap (Bot API limit is 4096; we leave headroom
# so a tool / verbose preamble can ride alongside without truncation).
_TELEGRAM_MESSAGE_CHARS = 4000

# Per-leaf preview cap inside a flattened webhook payload.  Long leaf
# values (commit messages, diff snippets) get tail-truncated so the
# prompt stays bounded even when individual fields are large.
_PAYLOAD_LEAF_PREVIEW_CHARS = 200


class AgentHandler:
    """Bus subscriber that runs an agent turn for webhook + scheduled events.

    Both event types collapse to the same shape: build a prompt,
    resolve the default provider, stream a turn (collecting just the
    text deltas), and publish an :class:`AgentResponseEvent` carrying
    the rendered text.

    This is intentionally a thin orchestration layer — it does NOT
    do tool composition, channel delivery, or persistence.  Each of
    those already lives in a single source of truth elsewhere in
    the codebase (``agent_tools.build_agent_tools``,
    ``app.channels``, ``crud.chat_message``).  A more sophisticated
    handler that persists a conversation row per fire is a follow-on.
    """

    def __init__(self, *, default_user_id: uuid.UUID | None = None) -> None:
        self._default_user_id = default_user_id

    def register(self, bus: Any) -> None:
        """Attach the agent handler to the bus.

        ``bus`` is typed loose so this module doesn't import the
        :class:`EventBus` concrete class — the bus protocol is just
        ``subscribe(event_type, handler)``.
        """
        bus.subscribe(WebhookEvent, self.handle_webhook)
        bus.subscribe(ScheduledEvent, self.handle_scheduled)

    async def handle_webhook(self, event: Event) -> None:
        """Build a prompt from the webhook payload + run a turn."""
        if not isinstance(event, WebhookEvent):
            return
        prompt = _build_webhook_prompt(event)
        target_chat_ids: list[str] = []
        await self._run_and_publish(
            prompt=prompt,
            user_id=event.user_id or self._default_user_id,
            target_chat_ids=target_chat_ids,
            originating_event_id=event.id,
        )

    async def handle_scheduled(self, event: Event) -> None:
        """Run the configured prompt + deliver to the job's target chats."""
        if not isinstance(event, ScheduledEvent):
            return
        prompt = event.prompt
        if event.skill_name:
            # CCT convention: surface the skill name as a slash-prefix
            # so the model picks it up the way users type a skill.
            prompt = f"/{event.skill_name}\n\n{prompt}" if prompt else f"/{event.skill_name}"

        notification_header = (
            f"[System Notification: Reminder Fired - {event.job_name}]"
            if event.job_name
            else "[System Notification: Reminder Fired]"
        )
        prompt = f"{notification_header}\n\n{prompt}"
        await self._run_and_publish(
            prompt=prompt,
            user_id=event.user_id or self._default_user_id,
            target_chat_ids=list(event.target_chat_ids),
            target_conversation_id=event.target_conversation_id,
            originating_event_id=event.id,
        )

    async def _run_and_publish(
        self,
        *,
        prompt: str,
        user_id: uuid.UUID | None,
        target_chat_ids: list[str],
        target_conversation_id: uuid.UUID | None = None,
        originating_event_id: str,
    ) -> None:
        """Stream a turn, persist it, publish an AgentResponseEvent.

        When ``target_conversation_id`` is provided, the rendered text is
        written into ``chat_messages`` as a finalised assistant turn
        *before* Telegram fan-out. The persist step is best-effort: if
        the conversation has been deleted or the write fails, the
        delivery to Telegram still happens so the user isn't silently
        denied the heartbeat output.
        """
        if user_id is None:
            logger.warning(
                "AGENT_HANDLER_NO_USER originating_event_id=%s; skipping",
                originating_event_id,
            )
            return
        try:
            text = await _run_agent_turn(prompt=prompt, user_id=user_id)
        except Exception:
            logger.exception(
                "AGENT_HANDLER_RUN_FAILED originating_event_id=%s user_id=%s",
                originating_event_id,
                user_id,
            )
            return
        if not text:
            logger.info(
                "AGENT_HANDLER_NO_OUTPUT originating_event_id=%s user_id=%s",
                originating_event_id,
                user_id,
            )
            return
        if target_conversation_id is not None:
            await _persist_assistant_response(
                conversation_id=target_conversation_id,
                user_id=user_id,
                text=text,
                originating_event_id=originating_event_id,
            )
        # Lazy import — keeps the handler module decoupled from the
        # bus-publish helper to avoid a circular import surface.
        from app.core.event_bus.global_bus import (  # noqa: PLC0415
            publish_if_available,
        )

        if target_chat_ids:
            for chat_id in target_chat_ids:
                await publish_if_available(
                    AgentResponseEvent(
                        user_id=user_id,
                        chat_id=chat_id,
                        text=text,
                        originating_event_id=originating_event_id,
                    )
                )
        else:
            # No explicit target — publish without a chat_id so the
            # NotificationService falls back to the configured
            # default broadcast list.
            await publish_if_available(
                AgentResponseEvent(
                    user_id=user_id,
                    chat_id=None,
                    text=text,
                    originating_event_id=originating_event_id,
                )
            )


class NotificationService:
    """Bus subscriber that delivers AgentResponseEvents to Telegram chats.

    Pulled out of the bot module so it can be exercised from a unit
    test with a mock bot.  The real bot instance comes off
    ``app.state.telegram_service`` — the lifespan passes it in at
    construction time.
    """

    def __init__(self, *, telegram_bot: Any | None) -> None:
        self._bot = telegram_bot

    def register(self, bus: Any) -> None:
        """Attach the delivery handler to the bus."""
        bus.subscribe(AgentResponseEvent, self.handle_response)

    async def handle_response(self, event: Event) -> None:
        """Deliver the response text to the configured Telegram chat(s)."""
        if not isinstance(event, AgentResponseEvent):
            return
        if self._bot is None:
            logger.debug(
                "NOTIFICATION_NO_BOT originating_event_id=%s",
                event.originating_event_id,
            )
            return

        text = (event.text or "").strip()
        if not text:
            return
        # Truncate to fit Telegram's per-message budget.  Splitting a
        # long agent response into multiple sends is a future refinement
        # — for now a single 4k tail is fine for webhook / scheduler
        # use cases.
        if len(text) > _TELEGRAM_MESSAGE_CHARS:
            text = text[:_TELEGRAM_MESSAGE_CHARS] + "…"

        target_chats = list(self._resolve_target_chats(event))
        for chat_id in target_chats:
            try:
                await self._bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                logger.exception(
                    "NOTIFICATION_DELIVERY_FAILED chat_id=%s originating_event_id=%s",
                    chat_id,
                    event.originating_event_id,
                )

    def _resolve_target_chats(self, event: AgentResponseEvent) -> Iterable[str]:
        """Pick which Telegram chats to deliver this response to."""
        if event.chat_id:
            yield event.chat_id
            return
        # Future: read default-chat-IDs list from settings; for now
        # an event without a target falls through silently so the
        # AgentHandler can still publish for audit / metrics
        # subscribers without forcing a Telegram side-effect.
        return


def _build_webhook_prompt(event: WebhookEvent) -> str:
    """Render a webhook payload as a model-readable prompt."""
    payload_summary = _flatten_payload(event.payload)
    return (
        f"A {event.provider} webhook event occurred.\n"
        f"Event type: {event.event_type_name}\n"
        f"Payload summary:\n{payload_summary}\n\n"
        "Summarise this event briefly.  Highlight anything that needs "
        "the user's attention."
    )


def _flatten_payload(payload: dict[str, Any], max_chars: int = _PAYLOAD_PROMPT_BUDGET_CHARS) -> str:
    """Compact the JSON payload into ``key: value`` lines for the prompt."""
    lines: list[str] = []
    _flatten_into(payload, lines)
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[:max_chars] + "\n... (truncated)"
    return text


def _format_leaf(value: Any) -> str:
    """Stringify a JSON leaf value with a single-leaf preview cap."""
    preview = str(value)
    if len(preview) > _PAYLOAD_LEAF_PREVIEW_CHARS:
        return preview[:_PAYLOAD_LEAF_PREVIEW_CHARS] + "..."
    return preview


def _flatten_into(
    data: Any,
    lines: list[str],
    prefix: str = "",
    depth: int = 0,
    max_depth: int = 2,
) -> None:
    """Walk a JSON value into ``key.subkey: value`` lines."""
    if depth >= max_depth:
        lines.append(f"{prefix}: ...")
        return
    if isinstance(data, dict):
        _flatten_dict(data, lines, prefix, depth, max_depth)
        return
    if isinstance(data, list):
        lines.append(f"{prefix}: [{len(data)} items]")
        for index, item in enumerate(data[:3]):
            _flatten_into(item, lines, f"{prefix}[{index}]", depth + 1, max_depth)
        return
    lines.append(f"{prefix}: {data}")


def _flatten_dict(
    data: dict[str, Any],
    lines: list[str],
    prefix: str,
    depth: int,
    max_depth: int,
) -> None:
    """Walk a dict child of ``_flatten_into``, kept separate to bound nesting depth."""
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict | list):
            _flatten_into(value, lines, full, depth + 1, max_depth)
        else:
            lines.append(f"{full}: {_format_leaf(value)}")


async def _run_agent_turn(*, prompt: str, user_id: uuid.UUID) -> str:
    """Stream one provider turn and return the concatenated assistant text.

    Resolves the catalog default model + the user's workspace + the
    standard tool composition.  Skips workspace tools when the user
    hasn't completed onboarding (no default workspace) — webhook /
    scheduled traffic shouldn't be gated on the onboarding flow.
    """
    # All imports are lazy so the bus module can be loaded without
    # pulling in the chat router's heavy dependency tree.
    from app.core.agent_loop.tools import build_agent_tools  # noqa: PLC0415
    from app.core.governance.permissions import (  # noqa: PLC0415
        PermissionContext,
        build_default_permission_check,
    )
    from app.core.governance.workspace_context import (  # noqa: PLC0415
        load_workspace_context,
    )
    from app.crud.workspace import get_default_workspace  # noqa: PLC0415

    async with async_session_maker() as session:
        workspace = await get_default_workspace(user_id, session)

    workspace_root: Path | None = Path(workspace.path) if workspace is not None else None
    workspace_ctx = load_workspace_context(workspace_root) if workspace_root is not None else None
    system_prompt = workspace_ctx.system_prompt if workspace_ctx is not None else None
    enabled_tools = workspace_ctx.enabled_tools if workspace_ctx is not None else None

    agent_tools = (
        build_agent_tools(
            workspace_root=workspace_root,
            user_id=user_id,
            send_fn=None,
            surface="webhook",
        )
        if workspace_root is not None
        else []
    )

    from app.core.agent_loop.types import (  # noqa: PLC0415
        PermissionCheckFn,
        PermissionCheckResult,
    )

    permission_check_fn: PermissionCheckFn | None = None
    if workspace_root is not None:
        permission_context = PermissionContext(
            user_id=str(user_id),
            workspace_root=workspace_root,
            conversation_id=str(uuid.uuid4()),
            surface="webhook",
            enabled_tools=enabled_tools,
        )
        gate = build_default_permission_check()

        async def permission_check_for_handler(
            tool_name: str, arguments: dict[str, Any]
        ) -> PermissionCheckResult:
            decision = await gate(tool_name, arguments, permission_context)
            return PermissionCheckResult(
                allow=decision.allow,
                reason=decision.reason,
                violation_type=decision.violation_type,
            )

        permission_check_fn = permission_check_for_handler

    # resolve_llm does not accept user_id; workspace_root carries the
    # per-user key resolution upstream. Kept for call-site symmetry.
    _ = user_id
    provider = resolve_llm(
        default_model().id,
        workspace_root=workspace_root,
    )

    accumulated: list[str] = [
        stream_event.get("content", "")
        async for stream_event in provider.stream(
            prompt,
            uuid.uuid4(),
            user_id,
            history=[],
            tools=agent_tools or None,
            system_prompt=system_prompt,
            permission_check=permission_check_fn,
        )
        if stream_event.get("type") == "delta"
    ]
    return "".join(accumulated).strip()


async def _persist_assistant_response(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    text: str,
    originating_event_id: str,
) -> None:
    """Write the agent's response into a chat conversation as a finalised turn.

    Lazy imports keep ``event_bus.handlers`` from pulling the
    chat-message CRUD into its module-load graph — the sentrux layer
    rule wants core code to avoid hard imports of ``app.crud.*``.

    Failures are logged and swallowed: a persistence error must not
    break the Telegram fan-out that follows in the caller. The row is
    written via the same helpers the web chat router uses, so the
    UI's existing ``GET .../messages`` path picks it up immediately.
    """
    from app.crud.chat_message import (  # noqa: PLC0415
        append_assistant_placeholder,
        finalize_assistant_message,
    )

    try:
        async with async_session_maker() as session:
            placeholder = await append_assistant_placeholder(
                session,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            await finalize_assistant_message(
                session,
                message_id=placeholder.id,
                content=text,
                thinking=None,
                tool_calls=None,
                timeline=None,
                thinking_duration_seconds=None,
                assistant_status="complete",
            )
            await session.commit()
    except Exception:
        logger.exception(
            "AGENT_HANDLER_PERSIST_FAILED conversation_id=%s originating_event_id=%s",
            conversation_id,
            originating_event_id,
        )
