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
    update_conversation_reasoning_effort,
    update_conversation_verbose_level,
)
from app.models import Conversation
from app.providers.base import ReasoningEffort

from .delivery import DEFAULT_VERBOSE_LEVEL

# Action function names echoed back in ``commonEventObject.invokedFunction``.
FN_SET_THINKING = "gchat_set_thinking"
FN_SET_VERBOSE = "gchat_set_verbose"
_PARAM_VALUE = "value"

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


def _coerce_verbose(value: str) -> int:
    try:
        return max(_VERBOSE_MIN, min(_VERBOSE_MAX, int(value)))
    except ValueError:
        return DEFAULT_VERBOSE_LEVEL


def _action_button(*, label: str, function: str, value: str, selected: bool) -> dict[str, Any]:
    return {
        "text": f"✓ {label}" if selected else label,
        "onClick": {
            "action": {
                "function": function,
                "parameters": [{"key": _PARAM_VALUE, "value": value}],
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
