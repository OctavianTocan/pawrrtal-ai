"""Tests for the Telegram ``/verbose`` inline-keyboard picker (#343 / #355)."""

from __future__ import annotations

import uuid

from app.integrations.telegram.verbose_picker import (
    VERBOSE_CALLBACK_PREFIX,
    VERBOSE_LEVELS,
    VerboseCallback,
    VerbosePickerState,
    build_verbose_keyboard,
    format_picker_text,
    parse_verbose_callback_data,
    verbose_label,
)

_FAKE_CONVERSATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _state(*, current: int | None = None, default: int = 1) -> VerbosePickerState:
    return VerbosePickerState(
        current_level=current,
        default_level=default,
        conversation_id=_FAKE_CONVERSATION_ID,
        user_id=_FAKE_USER_ID,
    )


def test_keyboard_lists_one_button_per_level() -> None:
    """The picker always exposes the three canonical levels (#343)."""
    rows = build_verbose_keyboard(_state())
    texts = [row[0].text for row in rows[: len(VERBOSE_LEVELS)]]
    assert texts == ["0 (quiet)", "1 (normal)", "2 (detailed)"]


def test_keyboard_marks_currently_selected_level() -> None:
    """A check mark precedes the rung currently saved on the conversation."""
    rows = build_verbose_keyboard(_state(current=2))
    selected = next(row for row in rows if row[0].text.startswith("✓ "))
    other = next(row for row in rows if row[0].text == "0 (quiet)")
    assert selected[0].text == "✓ 2 (detailed)"
    assert not other[0].text.startswith("✓ ")


def test_clear_button_only_appears_when_override_is_set() -> None:
    """Conversations on the default surface get three buttons; overridden get four."""
    rows_default = build_verbose_keyboard(_state(current=None))
    rows_override = build_verbose_keyboard(_state(current=0))
    assert len(rows_default) == len(VERBOSE_LEVELS)
    assert len(rows_override) == len(VERBOSE_LEVELS) + 1
    assert "default" in rows_override[-1][0].text


def test_select_callback_data_round_trips() -> None:
    """Selecting a rung produces a parseable ``vbs:s:<level>`` callback."""
    rows = build_verbose_keyboard(_state())
    parsed_levels = [
        parse_verbose_callback_data(row[0].callback_data) for row in rows[: len(VERBOSE_LEVELS)]
    ]
    actions = [callback.action for callback in parsed_levels if callback is not None]
    levels = [callback.level for callback in parsed_levels if callback is not None]
    assert actions == ["select", "select", "select"]
    assert levels == list(VERBOSE_LEVELS)


def test_clear_callback_data_round_trips() -> None:
    """The clear button produces a parseable ``vbs:c`` callback."""
    state = _state(current=1)
    clear_button = build_verbose_keyboard(state)[-1][0]
    parsed = parse_verbose_callback_data(clear_button.callback_data)
    assert parsed is not None
    assert parsed.action == "clear"
    assert parsed.level is None


def test_parse_rejects_unknown_callback_data() -> None:
    """Stale / malformed callbacks resolve to ``None``."""
    assert parse_verbose_callback_data(None) is None
    assert parse_verbose_callback_data("mdl:p") is None  # other picker
    assert parse_verbose_callback_data("vbs:s:42") is None  # out-of-range level
    assert parse_verbose_callback_data("vbs:s:xyz") is None  # non-numeric
    assert parse_verbose_callback_data("vbs:x") is None  # bogus action


def test_format_picker_text_shows_current_level() -> None:
    """The header surfaces the user's current rung in plain English."""
    text_current = format_picker_text(_state(current=2))
    assert "2 (detailed)" in text_current

    text_default = format_picker_text(_state(current=None, default=1))
    assert "default" in text_default
    assert "normal" in text_default


def test_callback_prefix_matches_runtime_dispatch() -> None:
    """``VERBOSE_CALLBACK_PREFIX`` lines up with the data emitted by buttons."""
    rows = build_verbose_keyboard(_state(current=0))
    for row in rows:
        assert row[0].callback_data.startswith(VERBOSE_CALLBACK_PREFIX)


def test_verbose_label_resolves_known_levels() -> None:
    """``verbose_label`` returns the human label for every valid rung."""
    assert verbose_label(0) == "quiet"
    assert verbose_label(1) == "normal"
    assert verbose_label(2) == "detailed"
    assert verbose_label(99) == "unknown"


def test_verbose_callback_constructor_accepts_keyword_arguments() -> None:
    """Sanity check: the dataclass is callable from the parser's perspective."""
    callback = VerboseCallback(action="select", level=1)
    assert callback.action == "select"
    assert callback.level == 1
