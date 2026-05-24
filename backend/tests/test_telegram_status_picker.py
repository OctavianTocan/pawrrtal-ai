"""Tests for the framework-free status-picker helpers (#361)."""

from __future__ import annotations

from collections.abc import Sequence

from app.integrations.telegram.status_picker import (
    STATUS_CALLBACK_PREFIX,
    StatusButton,
    StatusPanel,
    build_status_keyboard,
    panel_label,
    parse_status_callback_data,
    status_picker_header,
)


def _flatten(rows: Sequence[Sequence[StatusButton]]) -> list[StatusButton]:
    return [button for row in rows for button in row]


def test_keyboard_exposes_one_button_per_panel() -> None:
    """Every :class:`StatusPanel` member surfaces exactly once on the keyboard."""
    buttons = _flatten(build_status_keyboard())
    panels_in_keyboard = {parse_status_callback_data(b.callback_data) for b in buttons}
    panels_in_keyboard.discard(None)
    found = {result.panel for result in panels_in_keyboard if result is not None}
    assert found == set(StatusPanel)


def test_keyboard_labels_match_enum_order() -> None:
    """Labels render in declaration order so the keyboard layout is stable."""
    buttons = _flatten(build_status_keyboard())
    callback_panels = [parse_status_callback_data(b.callback_data) for b in buttons]
    panel_order = [parsed.panel for parsed in callback_panels if parsed is not None]
    assert panel_order == list(StatusPanel)


def test_keyboard_rows_have_at_most_two_buttons() -> None:
    """Two-column layout — mirrors the model picker's host screen."""
    for row in build_status_keyboard():
        assert 1 <= len(row) <= 2


def test_callback_data_fits_telegram_64_byte_cap() -> None:
    """Every status callback stays well under Telegram's 64-byte limit."""
    for button in _flatten(build_status_keyboard()):
        assert len(button.callback_data.encode("utf-8")) <= 64


def test_parse_callback_round_trips_panel() -> None:
    """Parsing each emitted callback produces the original panel back."""
    for button in _flatten(build_status_keyboard()):
        parsed = parse_status_callback_data(button.callback_data)
        assert parsed is not None
        # Re-encoding the parsed panel yields the same callback_data.
        assert button.callback_data == f"{STATUS_CALLBACK_PREFIX}{parsed.panel.value}"


def test_parse_rejects_unknown_panel_value() -> None:
    """Stale callbacks for retired / mistyped panels resolve to ``None``."""
    assert parse_status_callback_data(None) is None
    assert parse_status_callback_data("mdl:p") is None  # sibling picker
    assert parse_status_callback_data("sts:not-a-panel") is None
    assert parse_status_callback_data("sts:") is None


def test_panel_label_returns_human_readable_text() -> None:
    """Each panel has a non-empty, prefixed human label for ack text + buttons."""
    for panel in StatusPanel:
        label = panel_label(panel)
        assert label, f"{panel} has empty label"
        # Every label leads with a glyph + space + word, so the bare
        # discriminator slug never leaks into the UI.
        assert " " in label


def test_header_renders_friendly_copy() -> None:
    """Header is short, glyph-led, and not the discriminator slug."""
    text = status_picker_header()
    assert text.startswith("📊")
    assert "Pick a panel" in text
