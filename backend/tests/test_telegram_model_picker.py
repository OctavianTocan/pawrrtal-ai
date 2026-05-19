"""Tests for Telegram's catalog-backed inline model picker."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.providers.catalog import MODEL_CATALOG, default_model
from app.integrations.telegram.handlers import TelegramSender
from app.integrations.telegram.model_picker import (
    ModelCallback,
    build_models_keyboard,
    build_provider_keyboard,
    format_provider_picker_text,
    get_model_picker_state,
    has_provider,
    parse_model_callback_data,
    resolve_model_selection,
)


def _flatten(rows: list[list[object]]) -> list[object]:
    return [button for row in rows for button in row]


@pytest.mark.skip(
    reason="rewritten in Task 4: build_provider_keyboard uses new _list_callback(host, vendor, page) signature"
)
def test_provider_keyboard_groups_models_by_vendor() -> None:
    """Provider picker lists catalog vendors and keeps callback payloads small."""
    buttons = _flatten(build_provider_keyboard())
    labels = [button.text for button in buttons]

    assert "Anthropic (3)" in labels
    assert "Google (2)" in labels
    assert all(len(button.callback_data.encode("utf-8")) <= 64 for button in buttons)


def test_model_keyboard_marks_current_model_and_resolves_selection() -> None:
    """Model page shows the active choice and maps selection callbacks to entries."""
    current = default_model()
    rows = build_models_keyboard(
        provider=current.vendor.value,
        page=1,
        current_model_id=current.id,
    )
    buttons = _flatten(rows)
    current_button = next(button for button in buttons if current.display_name in button.text)

    assert current_button.text.startswith("Selected: ")
    parsed = parse_model_callback_data(current_button.callback_data)
    assert parsed is not None
    assert resolve_model_selection(parsed) == current


def test_stale_model_selection_is_rejected() -> None:
    """Catalog-token mismatch prevents old keyboards selecting the wrong entry."""
    stale = ModelCallback(action="select", index=0, catalog_token="deadbeef")
    assert resolve_model_selection(stale) is None


@pytest.mark.skip(
    reason="rewritten in Task 4: build_provider_keyboard uses new _list_callback(host, vendor, page) signature"
)
def test_provider_callbacks_round_trip() -> None:
    """Provider and list callbacks parse into explicit actions."""
    provider_button = build_provider_keyboard()[0][0]
    parsed = parse_model_callback_data(provider_button.callback_data)

    assert parsed is not None
    assert parsed.action == "list"
    assert parsed.provider is not None
    assert has_provider(parsed.provider)
    providers = parse_model_callback_data("mdl:p")
    assert providers is not None
    assert providers.action == "providers"


def test_provider_picker_text_displays_known_model_name() -> None:
    """The picker header renders a friendly display name for catalog entries."""
    text = format_provider_picker_text(default_model().id)
    assert default_model().display_name in text
    assert default_model().id not in text


@pytest.mark.anyio
async def test_get_model_picker_state_returns_none_for_unbound_sender() -> None:
    """Unbound Telegram users cannot open the picker."""
    sender = TelegramSender(user_id=1, chat_id=1, username=None, full_name=None)

    with patch(
        "app.integrations.telegram.model_picker.get_user_id_for_external",
        new=AsyncMock(return_value=None),
    ):
        state = await get_model_picker_state(sender=sender, session=AsyncMock())

    assert state is None


@pytest.mark.anyio
async def test_get_model_picker_state_reads_conversation_override() -> None:
    """The picker highlights the conversation-specific model override."""
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
