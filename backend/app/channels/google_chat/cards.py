"""Interactive Chat cards — thinking/verbose pickers via card buttons.

Telegram offers inline-keyboard pickers; Google Chat's equivalent is an
interactive card. A picker card is posted with ``cardsV2`` (each button's
``onClick.action`` names a handler function + parameters). The click arrives
on the SAME Pub/Sub subscription as messages —
``commonEventObject.invokedFunction`` + ``commonEventObject.parameters``, with
``chat.buttonClickedPayload.message.name`` identifying the card — so a Pub/Sub
app responds by patching that card (``updateMask=cardsV2``). The routing lives
in :mod:`app.channels.google_chat.ingress`.

v1 ships the small fixed-option pickers (thinking, verbose); model selection is
served by the ``/model <id>`` text command, since the catalog is far too large
for a flat button card.
"""

from __future__ import annotations

import uuid
from typing import Any, get_args

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import (
    update_conversation_model,
    update_conversation_reasoning_effort,
    update_conversation_verbose_level,
)
from app.models import Conversation
from app.providers.base import ReasoningEffort
from app.providers.catalog import MODEL_CATALOG

from .delivery import DEFAULT_VERBOSE_LEVEL

# Action function names echoed back in ``commonEventObject.invokedFunction``.
FN_SET_THINKING = "gchat_set_thinking"
FN_SET_VERBOSE = "gchat_set_verbose"
FN_MODEL_HOST = "gchat_model_host"
FN_SET_MODEL = "gchat_set_model"
_PARAM_VALUE = "value"
_PARAM_HOST = "host"
# The catalog has ~67 models; show at most this many per host, with an
# overflow note pointing at the `/model <id>` text command.
_MODEL_PER_HOST_CAP = 12

# "off" clears the reasoning override; the rest map to the ReasoningEffort literal.
_THINKING_CLEAR = "off"
_THINKING_OPTIONS: tuple[str, ...] = (*get_args(ReasoningEffort), _THINKING_CLEAR)
# (stored level, button label).
_VERBOSE_OPTIONS: tuple[tuple[int, str], ...] = ((0, "Quiet"), (1, "Tools"), (2, "Thinking"))
_VERBOSE_MIN, _VERBOSE_MAX = 0, 2


def picker_card_for(command: str, conversation: Conversation) -> list[dict[str, Any]] | None:
    """Return the picker card for a no-arg ``/command``, or ``None`` if not a picker."""
    if command == "thinking":
        return thinking_picker_card(conversation.reasoning_effort or _THINKING_CLEAR)
    if command == "verbose":
        level = (
            conversation.verbose_level
            if conversation.verbose_level is not None
            else DEFAULT_VERBOSE_LEVEL
        )
        return verbose_picker_card(level)
    if command == "model":
        return model_host_card(conversation.model_id)
    return None


async def apply_card_click(
    *,
    function: str,
    params: dict[str, str],
    user_id: uuid.UUID,
    conversation: Conversation,
    session: AsyncSession,
) -> list[dict[str, Any]] | None:
    """Apply a picker button click and return the refreshed card to patch.

    Returns ``None`` for an unknown function so the ingress leaves the card
    untouched.
    """
    value = params.get(_PARAM_VALUE, "")
    if function == FN_SET_THINKING:
        stored = None if value == _THINKING_CLEAR else value
        await update_conversation_reasoning_effort(
            conversation_id=conversation.id,
            user_id=user_id,
            reasoning_effort=stored,
            session=session,
        )
        return thinking_picker_card(value)
    if function == FN_SET_VERBOSE:
        level = _coerce_verbose(value)
        await update_conversation_verbose_level(
            conversation_id=conversation.id, verbose_level=level, session=session
        )
        return verbose_picker_card(level)
    if function == FN_MODEL_HOST:
        return model_list_card(params.get(_PARAM_HOST, ""), conversation.model_id)
    if function == FN_SET_MODEL:
        await update_conversation_model(
            conversation_id=conversation.id, model_id=value, session=session
        )
        return model_list_card(_host_of(value), value)
    return None


def thinking_picker_card(current: str) -> list[dict[str, Any]]:
    """Build the reasoning-effort picker card, marking *current* selected."""
    buttons = [
        _action_button(label=opt, function=FN_SET_THINKING, value=opt, selected=opt == current)
        for opt in _THINKING_OPTIONS
    ]
    return _picker_card(
        "thinking-picker", "Reasoning effort", f"Current: <b>{current}</b>", buttons
    )


def verbose_picker_card(current: int) -> list[dict[str, Any]]:
    """Build the verbosity picker card, marking *current* selected."""
    buttons = [
        _action_button(
            label=label, function=FN_SET_VERBOSE, value=str(level), selected=level == current
        )
        for level, label in _VERBOSE_OPTIONS
    ]
    label = dict(_VERBOSE_OPTIONS).get(current, "?")
    subtitle = f"Current: <b>{current} ({label})</b>"
    return _picker_card("verbose-picker", "Detail level", subtitle, buttons)


def model_host_card(current_id: str | None) -> list[dict[str, Any]]:
    """Build the first-level model picker — one button per host."""
    hosts = sorted({_host_of(entry.id) for entry in MODEL_CATALOG})
    buttons = [
        _action_button(
            label=host, function=FN_MODEL_HOST, value=host, selected=False, param_key=_PARAM_HOST
        )
        for host in hosts
    ]
    subtitle = f"Current: <b>{current_id or 'default'}</b>\nPick a host, then a model."
    return _picker_card("model-picker", "Model", subtitle, buttons)


def model_list_card(host: str, current_id: str | None) -> list[dict[str, Any]]:
    """Build the second-level model picker — models for *host* (capped)."""
    entries = [entry for entry in MODEL_CATALOG if _host_of(entry.id) == host]
    buttons = [
        _action_button(
            label=entry.short_name,
            function=FN_SET_MODEL,
            value=entry.id,
            selected=entry.id == current_id,
        )
        for entry in entries[:_MODEL_PER_HOST_CAP]
    ]
    subtitle = f"Host <b>{host}</b> — current: <b>{current_id or 'default'}</b>"
    overflow = len(entries) - _MODEL_PER_HOST_CAP
    if overflow > 0:
        subtitle += f"\n(+{overflow} more — use /model &lt;id&gt;)"
    return _picker_card("model-picker", "Model", subtitle, buttons)


def _host_of(model_id: str) -> str:
    """Return the host slug of a model id (the part before ``:``)."""
    return model_id.split(":", 1)[0]


def _coerce_verbose(value: str) -> int:
    try:
        return max(_VERBOSE_MIN, min(_VERBOSE_MAX, int(value)))
    except ValueError:
        return DEFAULT_VERBOSE_LEVEL


def _action_button(
    *, label: str, function: str, value: str, selected: bool, param_key: str = _PARAM_VALUE
) -> dict[str, Any]:
    return {
        "text": f"✓ {label}" if selected else label,
        "onClick": {
            "action": {
                "function": function,
                "parameters": [{"key": param_key, "value": value}],
            }
        },
    }


def _picker_card(
    card_id: str, title: str, subtitle_html: str, buttons: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "cardId": card_id,
            "card": {
                "header": {"title": title},
                "sections": [
                    {
                        "widgets": [
                            {"textParagraph": {"text": subtitle_html}},
                            {"buttonList": {"buttons": buttons}},
                        ]
                    }
                ],
            },
        }
    ]
