"""Tests for the Telegram ``/thinking`` reasoning-effort picker."""

from __future__ import annotations

import uuid

import pytest

from app.channels.telegram.thinking_picker import (
    THINKING_CALLBACK_PREFIX,
    ThinkingCallback,
    ThinkingPickerState,
    build_thinking_keyboard,
    catalog_token,
    format_picker_text,
    format_unsupported_text,
    model_supports_reasoning,
    parse_thinking_callback_data,
    resolve_select,
)
from app.core.providers.catalog import MODEL_CATALOG, ModelEntry, default_model, find
from app.core.providers.model_id import Host, parse_model_id


def _entry(host: Host, model: str) -> ModelEntry:
    """Resolve a catalog entry by host + model substring (for test brevity)."""
    for candidate in MODEL_CATALOG:
        if candidate.host is host and candidate.model == model:
            return candidate
    raise AssertionError(f"catalog entry not found for {host}:{model}")


_FAKE_CONVERSATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _claude_state(*, current: str | None = None) -> ThinkingPickerState:
    return ThinkingPickerState(
        model_entry=_entry(Host.agent_sdk, "claude-opus-4-7"),
        current_effort=current,
        conversation_id=_FAKE_CONVERSATION_ID,
        user_id=_FAKE_USER_ID,
    )


def _gemini_state(*, current: str | None = None) -> ThinkingPickerState:
    return ThinkingPickerState(
        model_entry=_entry(Host.google_ai, "gemini-3-flash-preview"),
        current_effort=current,
        conversation_id=_FAKE_CONVERSATION_ID,
        user_id=_FAKE_USER_ID,
    )


def _gpt_4o_state(*, current: str | None = None) -> ThinkingPickerState:
    """A model that genuinely doesn't honour reasoning levels."""
    return ThinkingPickerState(
        model_entry=_entry(Host.litellm, "gpt-4o"),
        current_effort=current,
        conversation_id=_FAKE_CONVERSATION_ID,
        user_id=_FAKE_USER_ID,
    )


def _grok_state(*, current: str | None = None) -> ThinkingPickerState:
    return ThinkingPickerState(
        model_entry=_entry(Host.xai, "grok-4.3"),
        current_effort=current,
        conversation_id=_FAKE_CONVERSATION_ID,
        user_id=_FAKE_USER_ID,
    )


# ---------------------------------------------------------------------------
# Catalog wiring
# ---------------------------------------------------------------------------


def test_catalog_exposes_supports_reasoning_per_model() -> None:
    """Every catalog entry has the new field with a deterministic value."""
    for entry in MODEL_CATALOG:
        assert isinstance(entry.supports_reasoning, tuple)


def test_claude_models_with_adaptive_thinking_expose_three_levels() -> None:
    """Claude's adaptive thinking ``effort`` enum is low/medium/high only.

    Opus 4.7 + Sonnet 4.6 support adaptive thinking; Haiku 4.5 only
    supports manual ``budget_tokens`` (no adaptive ``effort``) so we
    don't surface a picker for it.
    """
    for model in ("claude-opus-4-7", "claude-sonnet-4-6"):
        entry = _entry(Host.agent_sdk, model)
        assert entry.supports_reasoning == ("low", "medium", "high")


def test_claude_haiku_no_adaptive_thinking() -> None:
    """Haiku 4.5 supports extended thinking via budget_tokens only — no picker."""
    assert _entry(Host.agent_sdk, "claude-haiku-4-5").supports_reasoning == ()


def test_grok_exposes_minimal_low_high() -> None:
    """xai_provider._map_reasoning_effort spans three Grok 4.3 tiers.

    xAI added a no-thinking tier (``EFFORT_NONE``) to Grok 4.3 (issue
    #373). ``"minimal"`` maps to it; ``"low"`` and ``"medium"`` collapse
    to ``EFFORT_LOW``; ``"high"`` and ``"extra-high"`` collapse to
    ``EFFORT_HIGH``. The picker surfaces the three distinct tiers.
    """
    assert _entry(Host.xai, "grok-4.3").supports_reasoning == ("minimal", "low", "high")


def test_gemini_3_flash_models_expose_all_four_levels() -> None:
    """Per the Gemini 3 developer guide, every Flash-tier model accepts
    the full thinking_level enum (``minimal | low | medium | high``).
    Only 3.1 Pro omits ``minimal``.
    """
    flash_models = (
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
    )
    for model in flash_models:
        assert _entry(Host.google_ai, model).supports_reasoning == (
            "minimal",
            "low",
            "medium",
            "high",
        )


def test_gemini_3_pro_omits_minimal_level() -> None:
    """Gemini 3.1 Pro doesn't accept ``minimal`` (per the Gemini 3
    developer guide table); the three levels we surface are all it
    accepts."""
    assert _entry(Host.google_ai, "gemini-3.1-pro-preview").supports_reasoning == (
        "low",
        "medium",
        "high",
    )


def test_post_xhigh_cutoff_openai_models_expose_all_five_levels() -> None:
    """Per the openai-python ``Reasoning`` docstring, ``xhigh`` is
    accepted on models *after* ``gpt-5.1-codex-max``. That covers the
    5.3 chat + codex variants, the entire 5.4 series, and 5.5.
    ``minimal`` is OpenAI's lightest tier and is accepted on every
    reasoning-capable model.
    """
    for model in (
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5.3-chat-latest",
        "gpt-5.3-codex",
    ):
        entry = _entry(Host.litellm, model)
        assert entry.supports_reasoning == (
            "minimal",
            "low",
            "medium",
            "high",
            "extra-high",
        )


def test_pre_xhigh_cutoff_openai_reasoning_models_stay_at_four_levels() -> None:
    """``gpt-5.1-codex-max`` is the cutoff itself; earlier reasoning
    models (gpt-5/-mini/-nano, the o-series) cap at ``high`` and the
    resolver maps a stored ``extra-high`` down for them. They still
    accept ``minimal`` natively (the OpenAI enum has it on every
    reasoning model).
    """
    for model in (
        "gpt-5.1-codex-max",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "o3",
        "o3-mini",
        "o4-mini",
        "o1",
        "o1-mini",
    ):
        entry = _entry(Host.litellm, model)
        assert entry.supports_reasoning == ("minimal", "low", "medium", "high")


def test_non_reasoning_openai_models_have_empty_tuple() -> None:
    """gpt-4o, gpt-4.1 etc. are not reasoning models."""
    for model in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"):
        assert _entry(Host.litellm, model).supports_reasoning == ()


# ---------------------------------------------------------------------------
# Keyboard shape
# ---------------------------------------------------------------------------


def test_keyboard_shows_one_button_per_supported_level() -> None:
    """Claude exposes three levels (no ``extra-high``)."""
    state = _claude_state()
    rows = build_thinking_keyboard(state)
    assert len(rows) == 3
    texts = [row[0].text for row in rows]
    assert texts == ["low", "medium", "high"]


def test_keyboard_marks_currently_selected_level() -> None:
    state = _claude_state(current="high")
    rows = build_thinking_keyboard(state)
    # Selected row is prefixed with the check-mark; siblings are not.
    high_row = next(
        row for row in rows if "high" in row[0].text and "extra-high" not in row[0].text
    )
    other_row = next(row for row in rows if row[0].text == "low")
    assert high_row[0].text.startswith("✓ ")
    assert not other_row[0].text.startswith("✓ ")


def test_clear_button_only_appears_when_override_is_set() -> None:
    no_override_rows = build_thinking_keyboard(_claude_state())
    overridden_rows = build_thinking_keyboard(_claude_state(current="low"))

    # No override → no clear button → 4 rows (one per level).
    assert all("Clear override" not in row[0].text for row in no_override_rows)
    # Override set → clear button row is appended at the end.
    assert "Clear override" in overridden_rows[-1][0].text


def test_callback_payloads_fit_telegram_64_byte_limit() -> None:
    """Telegram caps inline-button callback_data at 64 bytes."""
    rows = build_thinking_keyboard(_claude_state(current="high"))
    for row in rows:
        for button in row:
            assert len(button.callback_data.encode("utf-8")) <= 64


def test_select_callback_carries_catalog_token_for_staleness_detection() -> None:
    rows = build_thinking_keyboard(_claude_state())
    for row in rows:
        button = row[0]
        parsed = parse_thinking_callback_data(button.callback_data)
        assert parsed is not None
        assert parsed.catalog_token == catalog_token()


# ---------------------------------------------------------------------------
# Per-model branching
# ---------------------------------------------------------------------------


def test_gpt_4o_picker_state_reports_unsupported() -> None:
    """GPT-4o doesn't honour reasoning levels — the picker says so."""
    state = _gpt_4o_state()
    assert model_supports_reasoning(state) is False


def test_gemini_picker_state_reports_supported() -> None:
    """Gemini 3 honours thinking_level — supported through the provider mapping."""
    assert model_supports_reasoning(_gemini_state()) is True


def test_grok_picker_shows_three_buttons() -> None:
    """Grok 4.3's picker now surfaces ``minimal | low | high`` after
    xAI shipped the no-thinking tier (issue #373).
    """
    state = _grok_state()
    rows = build_thinking_keyboard(state)
    assert [row[0].text for row in rows] == ["minimal", "low", "high"]


def test_grok_picker_minimal_button_maps_to_no_thinking_for_xai() -> None:
    """A ``minimal`` callback for Grok 4.3 resolves through
    ``_map_reasoning_effort`` to ``EFFORT_NONE`` — the new
    no-thinking tier (issue #373). Crossing the integration
    boundary here keeps the picker UI and the provider mapping
    locked in step.
    """
    from app.core.providers.xai.provider import _map_reasoning_effort

    try:
        from xai_sdk.proto.v6 import chat_pb2
    except ImportError:  # pragma: no cover — xai-sdk pin variance
        from xai_sdk.proto.v5 import chat_pb2

    assert _map_reasoning_effort("minimal") == chat_pb2.ReasoningEffort.EFFORT_NONE


def test_unsupported_text_mentions_the_model() -> None:
    text = format_unsupported_text(_gpt_4o_state())
    assert "GPT-4o" in text


def test_picker_header_shows_current_label_when_set() -> None:
    text = format_picker_text(_claude_state(current="medium"))
    assert "medium" in text
    assert "Claude Opus" in text


def test_picker_header_shows_default_label_when_unset() -> None:
    text = format_picker_text(_claude_state())
    assert "default" in text.lower()


# ---------------------------------------------------------------------------
# Callback parsing + resolution
# ---------------------------------------------------------------------------


def test_parse_select_callback_round_trip() -> None:
    rows = build_thinking_keyboard(_claude_state())
    medium_button = next(row[0] for row in rows if row[0].text == "medium")
    parsed = parse_thinking_callback_data(medium_button.callback_data)
    assert parsed is not None
    assert parsed.action == "select"
    assert parsed.effort == "medium"


def test_parse_clear_callback_round_trip() -> None:
    rows = build_thinking_keyboard(_claude_state(current="low"))
    clear_button = rows[-1][0]
    parsed = parse_thinking_callback_data(clear_button.callback_data)
    assert parsed is not None
    assert parsed.action == "clear"


def test_parse_returns_none_for_unrelated_callback() -> None:
    assert parse_thinking_callback_data("mdl:p") is None
    assert parse_thinking_callback_data(None) is None
    assert parse_thinking_callback_data(f"{THINKING_CALLBACK_PREFIX}bogus") is None


def test_resolve_select_rejects_stale_catalog_token() -> None:
    entry = _entry(Host.agent_sdk, "claude-opus-4-7")
    stale = ThinkingCallback(action="select", catalog_token="deadbeef", effort="medium")
    assert resolve_select(stale, entry=entry) is None


def test_resolve_select_rejects_effort_not_supported_by_model() -> None:
    entry = _entry(Host.xai, "grok-4.3")  # minimal + low + high
    callback = ThinkingCallback(action="select", catalog_token=catalog_token(), effort="medium")
    assert resolve_select(callback, entry=entry) is None


def test_resolve_select_returns_effort_for_valid_callback() -> None:
    """``high`` survives the catalog-tuple check on every reasoning model."""
    entry = _entry(Host.litellm, "gpt-5")
    callback = ThinkingCallback(action="select", catalog_token=catalog_token(), effort="high")
    assert resolve_select(callback, entry=entry) == "high"


def test_resolve_select_rejects_effort_outside_catalog_tuple() -> None:
    """``extra-high`` isn't in any catalog row, so the picker rejects it.

    The chat-router resolver still adapts an ``extra-high`` *stored*
    value to the catalog's nearest supported level — but the picker
    UI only displays buttons for tuple members, and the callback
    validator refuses anything else.
    """
    entry = _entry(Host.litellm, "gpt-5")
    callback = ThinkingCallback(action="select", catalog_token=catalog_token(), effort="extra-high")
    assert resolve_select(callback, entry=entry) is None


# ---------------------------------------------------------------------------
# Default-model fallback
# ---------------------------------------------------------------------------


def test_default_model_resolution_via_catalog() -> None:
    """The picker resolves the catalog default when conversation.model_id is NULL."""
    default = default_model()
    parsed = parse_model_id(default.id)
    entry = find(parsed)
    assert entry is default


@pytest.mark.parametrize(
    "model_name",
    ["claude-opus-4-7", "grok-4.3", "o1"],
)
def test_supports_reasoning_states_match_keyboard_levels(model_name: str) -> None:
    """The keyboard's level list is exactly the catalog field."""
    entry = next(e for e in MODEL_CATALOG if e.model == model_name)
    state = ThinkingPickerState(
        model_entry=entry,
        current_effort=None,
        conversation_id=_FAKE_CONVERSATION_ID,
        user_id=_FAKE_USER_ID,
    )
    keyboard_labels = [row[0].text for row in build_thinking_keyboard(state)]
    assert keyboard_labels == list(entry.supports_reasoning)
