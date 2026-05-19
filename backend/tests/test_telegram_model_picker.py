"""Tests for Telegram's catalog-backed inline model picker."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.providers.catalog import MODEL_CATALOG, default_model
from app.core.providers.model_id import Host
from app.integrations.telegram.model_picker import (
    ModelCallback,
    build_host_keyboard,
    build_models_keyboard,
    build_vendor_keyboard,
    format_host_picker_text,
    format_models_picker_text,
    format_vendor_picker_text,
    get_model_picker_state,
    has_host,
    has_vendor_in_host,
    parse_model_callback_data,
    resolve_model_selection,
)
from app.integrations.telegram.sender import TelegramSender


def _flatten(rows: list[list[object]]) -> list[object]:
    return [button for row in rows for button in row]


def test_host_keyboard_lists_all_hosts_with_friendly_labels() -> None:
    buttons = _flatten(build_host_keyboard())
    labels = [button.text for button in buttons]

    assert "Anthropic Agent SDK (3)" in labels
    assert "Gemini API (2)" in labels
    assert "xAI (1)" in labels
    assert "LiteLLM (5)" in labels
    assert "OpenCode Go (2)" in labels
    # Title-casing bug from before: must not contain the broken labels.
    assert "Openai (5)" not in labels
    assert "Xai (1)" not in labels
    assert "Zai (1)" not in labels
    assert all(len(button.callback_data.encode("utf-8")) <= 64 for button in buttons)


def test_host_button_for_single_vendor_jumps_to_model_list() -> None:
    """Hosts with exactly one vendor must skip the vendor screen."""
    button = next(
        b for b in _flatten(build_host_keyboard()) if b.text.startswith("Anthropic Agent SDK")
    )
    parsed = parse_model_callback_data(button.callback_data)

    assert parsed is not None
    assert parsed.action == "list"
    assert parsed.host == Host.agent_sdk.value
    assert parsed.provider == "anthropic"
    assert parsed.page == 1


def test_host_button_for_multi_vendor_opens_vendor_screen() -> None:
    """Hosts with multiple vendors must open the vendor screen."""
    button = next(b for b in _flatten(build_host_keyboard()) if b.text.startswith("OpenCode Go"))
    parsed = parse_model_callback_data(button.callback_data)

    assert parsed is not None
    assert parsed.action == "vendors"
    assert parsed.host == Host.opencode_go.value


def test_vendor_keyboard_lists_vendors_for_a_host() -> None:
    rows = build_vendor_keyboard(host=Host.opencode_go.value)
    labels = [b.text for b in _flatten(rows)]

    assert "Z.AI (1)" in labels
    assert "Moonshot (1)" in labels


def test_vendor_keyboard_back_button_returns_to_host_screen() -> None:
    rows = build_vendor_keyboard(host=Host.opencode_go.value)
    back_button = rows[-1][0]

    assert back_button.text == "Back to providers"
    parsed = parse_model_callback_data(back_button.callback_data)
    assert parsed is not None
    assert parsed.action == "providers"


def test_model_keyboard_marks_current_and_resolves_selection() -> None:
    current = default_model()
    rows = build_models_keyboard(
        host=current.host.value,
        vendor=current.vendor.value,
        page=1,
        current_model_id=current.id,
    )
    buttons = _flatten(rows)
    current_button = next(b for b in buttons if current.display_name in b.text)

    assert current_button.text.startswith("Selected: ")
    parsed = parse_model_callback_data(current_button.callback_data)
    assert parsed is not None
    assert resolve_model_selection(parsed) == current


def test_model_keyboard_back_button_for_multi_vendor_goes_to_vendor_screen() -> None:
    """OpenCode Go has multiple vendors — back must land on the vendor screen."""
    rows = build_models_keyboard(
        host=Host.opencode_go.value,
        vendor="zai",
        page=1,
        current_model_id="",
    )
    back_button = rows[-1][0]

    assert back_button.text == "Back to vendors"
    parsed = parse_model_callback_data(back_button.callback_data)
    assert parsed is not None
    assert parsed.action == "vendors"
    assert parsed.host == Host.opencode_go.value


def test_model_keyboard_back_button_for_single_vendor_goes_to_host_screen() -> None:
    """Anthropic Agent SDK has one vendor — back skips the vendor screen."""
    rows = build_models_keyboard(
        host=Host.agent_sdk.value,
        vendor="anthropic",
        page=1,
        current_model_id="",
    )
    back_button = rows[-1][0]

    assert back_button.text == "Back to providers"
    parsed = parse_model_callback_data(back_button.callback_data)
    assert parsed is not None
    assert parsed.action == "providers"


def test_stale_model_selection_is_rejected() -> None:
    stale = ModelCallback(action="select", index=0, catalog_token="deadbeef")
    assert resolve_model_selection(stale) is None


def test_has_host_and_has_vendor_in_host_guards() -> None:
    assert has_host(Host.agent_sdk.value) is True
    assert has_host("totally-fake") is False
    assert has_vendor_in_host(host=Host.opencode_go.value, vendor="zai") is True
    assert has_vendor_in_host(host=Host.opencode_go.value, vendor="anthropic") is False


def test_host_picker_text_displays_known_model_name() -> None:
    text = format_host_picker_text(default_model().id)
    assert default_model().display_name in text
    assert default_model().id not in text


def test_vendor_picker_text_includes_host_label() -> None:
    text = format_vendor_picker_text(host=Host.opencode_go.value)
    assert "OpenCode Go" in text


def test_models_picker_text_includes_host_and_vendor_labels() -> None:
    text = format_models_picker_text(
        host=Host.opencode_go.value,
        vendor="zai",
        page=1,
    )
    assert "OpenCode Go" in text
    assert "Z.AI" in text


@pytest.mark.anyio
async def test_get_model_picker_state_returns_none_for_unbound_sender() -> None:
    sender = TelegramSender(user_id=1, chat_id=1, username=None, full_name=None)

    with patch(
        "app.integrations.telegram.model_picker.get_user_id_for_external",
        new=AsyncMock(return_value=None),
    ):
        state = await get_model_picker_state(sender=sender, session=AsyncMock())

    assert state is None


@pytest.mark.anyio
async def test_get_model_picker_state_reads_conversation_override() -> None:
    sender = TelegramSender(user_id=2, chat_id=2, username=None, full_name=None, thread_id=9)
    override = MODEL_CATALOG[0].id
    conversation = SimpleNamespace(model_id=override)

    with (
        patch(
            "app.integrations.telegram.model_picker.get_user_id_for_external",
            new=AsyncMock(return_value=uuid.uuid4()),
        ),
        patch(
            "app.integrations.telegram.model_picker.get_or_create_telegram_conversation_full",
            new=AsyncMock(return_value=conversation),
        ),
    ):
        state = await get_model_picker_state(sender=sender, session=AsyncMock())

    assert state is not None
    assert state.current_model_id == override


def test_parse_vendor_callback_round_trips_host() -> None:
    parsed = parse_model_callback_data("mdl:v:opencode-go")
    assert parsed is not None
    assert parsed.action == "vendors"
    assert parsed.host == "opencode-go"


def test_parse_list_callback_round_trips_host_and_vendor() -> None:
    parsed = parse_model_callback_data("mdl:l:opencode-go:zai:2")
    assert parsed is not None
    assert parsed.action == "list"
    assert parsed.host == "opencode-go"
    assert parsed.provider == "zai"
    assert parsed.page == 2


def test_parse_legacy_list_callback_without_host_returns_none() -> None:
    """Old keyboards from before the host segment was added must be treated as stale.

    Selection callbacks (``mdl:s:<token>:<index>``) still resolve correctly
    because the catalog-token guards them; list keyboards are cheap to
    re-open so we don't keep backwards-compat parsing for them.
    """
    assert parse_model_callback_data("mdl:l:anthropic:1") is None


def test_pagination_first_page_omits_prev_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """First page must not emit a < Prev button — taking it produces a stale alert."""
    import app.integrations.telegram.model_picker as picker_module

    monkeypatch.setattr(picker_module, "_MODEL_PAGE_SIZE", 1)
    rows = build_models_keyboard(
        host=Host.litellm.value,
        vendor="openai",
        page=1,
        current_model_id="",
    )
    labels = [b.text for b in _flatten(rows)]
    assert "< Prev" not in labels
    assert "Next >" in labels


def test_pagination_last_page_omits_next_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """Last page must not emit a Next > button."""
    import app.integrations.telegram.model_picker as picker_module

    monkeypatch.setattr(picker_module, "_MODEL_PAGE_SIZE", 1)
    rows = build_models_keyboard(
        host=Host.litellm.value,
        vendor="openai",
        page=5,  # LiteLLM has 5 OpenAI models, so page 5 of 5 with size 1
        current_model_id="",
    )
    labels = [b.text for b in _flatten(rows)]
    assert "< Prev" in labels
    assert "Next >" not in labels
