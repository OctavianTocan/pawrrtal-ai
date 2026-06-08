"""Google Chat channel — pull loop + click-space resolution (ingress).

A card click carries its space under ``buttonClickedPayload`` (not
``messagePayload``), and the pull loop must acknowledge a message BEFORE its
(potentially slow) turn runs — otherwise Pub/Sub redelivers mid-turn and the
user gets a duplicate reply.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.channels.google_chat.messages import space_name
from tests.channels.google_chat.helpers import SPACE, addon_event, click_event, pubsub_envelope

pytestmark = pytest.mark.anyio


def test_space_name_resolved_from_button_click() -> None:
    # A card click carries its space under buttonClickedPayload, not messagePayload.
    event = click_event(function="gchat_set_verbose", value="2")
    assert space_name(event) == SPACE


async def test_pull_once_acks_before_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    # H1 regression guard: messages must be acked BEFORE their (potentially
    # slow) turns run, or Pub/Sub redelivers mid-turn → duplicate replies.
    import app.channels.google_chat.ingress as ingress_module

    order: list[str] = []

    async def _fake_pull(**_kwargs: Any) -> list[dict[str, Any]]:
        return [pubsub_envelope(addon_event())]

    async def _fake_ack(**_kwargs: Any) -> None:
        order.append("ack")

    async def _fake_handle(_event: dict[str, Any] | None) -> None:
        order.append("handle")

    monkeypatch.setattr(ingress_module, "pull_messages", _fake_pull)
    monkeypatch.setattr(ingress_module, "acknowledge", _fake_ack)
    monkeypatch.setattr(ingress_module, "_maybe_handle", _fake_handle)

    assert await ingress_module._pull_once() is True
    assert order == ["ack", "handle"]
