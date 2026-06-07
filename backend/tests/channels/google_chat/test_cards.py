"""Google Chat channel — interactive card pickers / button clicks (cards).

Covers click-field extraction, the thinking/verbose/model picker cards, and
``apply_card_click`` (set verbose, set/clear thinking, model host drill-down,
set model, unknown-function no-op).
"""

from __future__ import annotations

import pytest

from app.channels.google_chat.cards import (
    FN_MODEL_HOST,
    FN_SET_MODEL,
    FN_SET_THINKING,
    FN_SET_VERBOSE,
    apply_card_click,
    model_host_card,
    picker_card_for,
    thinking_picker_card,
    verbose_picker_card,
)
from app.channels.google_chat.commands import CommandContext
from app.channels.google_chat.messages import (
    clicked_message_name,
    invoked_function,
    invoked_parameters,
)
from tests.channels.google_chat.helpers import SPACE, addon_event, click_event, picker_buttons

pytestmark = pytest.mark.anyio


def test_invoked_function_reads_click() -> None:
    event = click_event(function="gchat_set_verbose", value="2")
    assert invoked_function(event) == "gchat_set_verbose"
    assert invoked_parameters(event) == {"value": "2"}
    assert clicked_message_name(event) == f"{SPACE}/messages/CARD"


def test_invoked_function_empty_for_plain_message() -> None:
    assert invoked_function(addon_event()) == ""


def test_thinking_picker_card_marks_current_and_targets_handler() -> None:
    buttons = picker_buttons(thinking_picker_card("high"))
    assert any(b["text"] == "✓ high" for b in buttons)
    assert all(b["onClick"]["action"]["function"] == FN_SET_THINKING for b in buttons)


def test_verbose_picker_card_marks_current_and_targets_handler() -> None:
    buttons = picker_buttons(verbose_picker_card(1))
    assert any(b["text"].startswith("✓") for b in buttons)
    assert all(b["onClick"]["action"]["function"] == FN_SET_VERBOSE for b in buttons)


async def test_picker_card_for_picker_vs_non_picker(command_ctx: CommandContext) -> None:
    assert picker_card_for("thinking", command_ctx.conversation) is not None
    assert picker_card_for("verbose", command_ctx.conversation) is not None
    assert picker_card_for("status", command_ctx.conversation) is None


async def test_apply_card_click_sets_verbose(command_ctx: CommandContext) -> None:
    cards = await apply_card_click(
        function=FN_SET_VERBOSE,
        params={"value": "2"},
        user_id=command_ctx.user_id,
        conversation=command_ctx.conversation,
        session=command_ctx.session,
    )
    assert cards is not None
    assert command_ctx.conversation.verbose_level == 2


async def test_apply_card_click_sets_then_clears_thinking(command_ctx: CommandContext) -> None:
    await apply_card_click(
        function=FN_SET_THINKING,
        params={"value": "high"},
        user_id=command_ctx.user_id,
        conversation=command_ctx.conversation,
        session=command_ctx.session,
    )
    assert command_ctx.conversation.reasoning_effort == "high"
    await apply_card_click(
        function=FN_SET_THINKING,
        params={"value": "off"},
        user_id=command_ctx.user_id,
        conversation=command_ctx.conversation,
        session=command_ctx.session,
    )
    assert command_ctx.conversation.reasoning_effort is None


async def test_apply_card_click_unknown_function_returns_none(command_ctx: CommandContext) -> None:
    cards = await apply_card_click(
        function="not_a_handler",
        params={},
        user_id=command_ctx.user_id,
        conversation=command_ctx.conversation,
        session=command_ctx.session,
    )
    assert cards is None


def test_model_host_card_targets_host_handler() -> None:
    buttons = picker_buttons(model_host_card(None))
    assert buttons
    assert all(b["onClick"]["action"]["function"] == FN_MODEL_HOST for b in buttons)


def test_model_host_card_filters_unauthenticated_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.channels.google_chat import cards as cards_module
    from app.providers.model_id import Host

    monkeypatch.setattr(
        cards_module,
        "host_authenticated",
        lambda host, *, workspace_root=None: host is Host.openai_codex,
    )

    buttons = picker_buttons(model_host_card(None))
    values = [button["onClick"]["action"]["parameters"][0]["value"] for button in buttons]
    assert values == [Host.openai_codex.value]


async def test_picker_card_for_model(command_ctx: CommandContext) -> None:
    assert picker_card_for("model", command_ctx.conversation) is not None


async def test_apply_card_click_model_host_drills_down(command_ctx: CommandContext) -> None:
    from app.providers.catalog import MODEL_CATALOG
    from app.providers.model_id import Host

    model = next(entry for entry in MODEL_CATALOG if entry.host is Host.openai_codex)
    cards = await apply_card_click(
        function=FN_MODEL_HOST,
        params={"host": model.host.value},
        user_id=command_ctx.user_id,
        conversation=command_ctx.conversation,
        session=command_ctx.session,
    )
    assert cards is not None
    assert all(b["onClick"]["action"]["function"] == FN_SET_MODEL for b in picker_buttons(cards))


async def test_apply_card_click_set_model_persists(command_ctx: CommandContext) -> None:
    from app.providers.catalog import MODEL_CATALOG
    from app.providers.model_id import Host

    model_id = next(entry.id for entry in MODEL_CATALOG if entry.host is Host.openai_codex)
    cards = await apply_card_click(
        function=FN_SET_MODEL,
        params={"value": model_id},
        user_id=command_ctx.user_id,
        conversation=command_ctx.conversation,
        session=command_ctx.session,
    )
    assert cards is not None
    assert command_ctx.conversation.model_id == model_id


async def test_apply_card_click_set_model_rejects_unauthenticated_model(
    monkeypatch: pytest.MonkeyPatch,
    command_ctx: CommandContext,
) -> None:
    from app.channels.google_chat import cards as cards_module
    from app.providers.catalog import MODEL_CATALOG

    model_id = MODEL_CATALOG[0].id
    monkeypatch.setattr(
        cards_module,
        "host_authenticated",
        lambda _host, *, workspace_root=None: False,
    )

    cards = await apply_card_click(
        function=FN_SET_MODEL,
        params={"value": model_id},
        user_id=command_ctx.user_id,
        conversation=command_ctx.conversation,
        session=command_ctx.session,
    )

    assert cards is not None
    assert command_ctx.conversation.model_id is None
