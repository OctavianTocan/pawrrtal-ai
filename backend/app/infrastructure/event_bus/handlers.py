"""Event-bus subscribers for agent execution."""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from app.infrastructure.database.legacy import async_session_maker
from app.infrastructure.event_bus.bus import Event
from app.infrastructure.event_bus.types import (
    AgentResponseEvent,
    ScheduledEvent,
    WebhookEvent,
)

logger = logging.getLogger(__name__)

# How many characters of the webhook payload to flatten into the prompt.
# Past this we truncate so a noisy GitHub payload can't blow the model
# context in one go.
_PAYLOAD_PROMPT_BUDGET_CHARS = 2000

# Per-leaf preview cap inside a flattened webhook payload.  Long leaf
# values (commit messages, diff snippets) get tail-truncated so the
# prompt stays bounded even when individual fields are large.
_PAYLOAD_LEAF_PREVIEW_CHARS = 200


class AgentHandler:
    """Bus subscriber that runs an agent turn for webhook + scheduled events.

    Targeted events collapse to the same shape: build a prompt, run it
    through the Turn Pipeline using a system delivery adapter, then
    publish an :class:`AgentResponseEvent` carrying the rendered text.

    This stays a thin orchestration layer. Provider resolution, tool
    composition, provider sessions, context providers, persistence,
    finalization, and cost accounting belong to the Turn Pipeline.
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
        """Run a targeted turn and publish its text as an AgentResponseEvent.

        ``target_conversation_id`` is required because the Turn Pipeline
        persists the user turn and assistant placeholder against a real
        conversation. Untargeted webhook traffic is skipped until the
        product has a deliberate destination for system-originated turns.
        """
        if user_id is None:
            logger.warning(
                "AGENT_HANDLER_NO_USER originating_event_id=%s; skipping",
                originating_event_id,
            )
            return
        if target_conversation_id is None:
            logger.warning(
                "AGENT_HANDLER_NO_TARGET_CONVERSATION originating_event_id=%s user_id=%s; skipping",
                originating_event_id,
                user_id,
            )
            return
        try:
            text = await _run_agent_turn(
                prompt=prompt,
                user_id=user_id,
                conversation_id=target_conversation_id,
                originating_event_id=originating_event_id,
            )
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
        # Lazy import — keeps the handler module decoupled from the
        # bus-publish helper to avoid a circular import surface.
        from app.infrastructure.event_bus.global_bus import (  # noqa: PLC0415
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
            await publish_if_available(
                AgentResponseEvent(
                    user_id=user_id,
                    chat_id=None,
                    text=text,
                    originating_event_id=originating_event_id,
                )
            )


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


async def _run_agent_turn(
    *,
    prompt: str,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    originating_event_id: str,
) -> str:
    """Run one targeted event through the Turn Pipeline and return text."""
    from pathlib import Path  # noqa: PLC0415

    from app.conversations.crud import get_conversation  # noqa: PLC0415
    from app.providers.base import ReasoningEffort  # noqa: PLC0415
    from app.providers.selection import default_model_id  # noqa: PLC0415
    from app.turns.pipeline import TurnCommand, prepare_turn, run_prepared_turn  # noqa: PLC0415
    from app.turns.pipeline.delivery import SystemDeliveryAdapter  # noqa: PLC0415
    from app.workspace.crud import get_default_workspace  # noqa: PLC0415

    async with async_session_maker() as session:
        workspace = await get_default_workspace(user_id, session)
        conversation = await get_conversation(user_id, session, conversation_id)

    if conversation is None:
        logger.warning(
            "AGENT_HANDLER_TARGET_CONVERSATION_MISSING conversation_id=%s originating_event_id=%s",
            conversation_id,
            originating_event_id,
        )
        return ""

    workspace_root = Path(workspace.path) if workspace is not None else None
    delivery = SystemDeliveryAdapter()
    prepared_turn = await prepare_turn(
        TurnCommand(
            conversation_id=conversation_id,
            user_id=user_id,
            question=prompt,
            workspace_root=workspace_root,
            workspace_id=workspace.id if workspace is not None else None,
            surface=delivery.surface,
            model_id=conversation.model_id or default_model_id(),
            reasoning_effort=cast(ReasoningEffort | None, conversation.reasoning_effort),
            request_id=originating_event_id,
            channel_metadata={
                "originating_event_id": originating_event_id,
                "source": "event_bus",
            },
            delivery_adapter=delivery,
            verbose_level=conversation.verbose_level,
        )
    )
    async for _chunk in run_prepared_turn(prepared_turn):
        pass
    return delivery.final_text
