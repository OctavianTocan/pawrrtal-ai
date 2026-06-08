"""Shared resolution helper for Telegram model selection.

Every Telegram surface that needs to know "which model is this
conversation using right now" walks the same fallback chain:

1. ``Conversation.model_id`` (per-conversation override set via the
   picker, ``/model``, or the chat router).
2. The provider-selection default model.

Centralising the chain in one helper avoids the drift that surfaces
when ``/thinking``, ``/compact``, ``/status``, and the chat path
each open-code the resolution differently — a known footgun before
this module existed.
"""

from __future__ import annotations

from app.providers.selection import effective_model_id


def resolve_effective_model_id(*, conversation_model_id: str | None) -> str:
    """Resolve the effective canonical model_id for a Telegram conversation.

    Order: conversation override → provider-selection default.
    """
    return effective_model_id(conversation_model_id=conversation_model_id)
