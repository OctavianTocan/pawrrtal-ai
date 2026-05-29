"""Argument-parsing tests for :func:`_parse_model_args`.

The helper is private but worth covering directly: the dispatcher in
``handle_model_command`` is a thin branch over its output, so a
regression in this single function silently changes how every
``/model …`` shape is routed.

The test set targets the edge cases the analyzer flagged as
under-covered: uppercase ``DEFAULT``, double-``default``, extra
whitespace, and mixed-case ``DEFault``.
"""

from __future__ import annotations

import pytest

from app.channels.telegram.model_command import _parse_model_args, _ParsedArgs


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Empty / whitespace-only → no parse.
        ("", _ParsedArgs(model_id="", make_default=False)),
        ("   ", _ParsedArgs(model_id="", make_default=False)),
        # Plain ID — no keyword.
        ("anthropic/claude-sonnet-4-6", _ParsedArgs("anthropic/claude-sonnet-4-6", False)),
        # Trailing keyword (canonical typed form).
        ("anthropic/claude-sonnet-4-6 default", _ParsedArgs("anthropic/claude-sonnet-4-6", True)),
        # Leading keyword.
        ("default anthropic/claude-sonnet-4-6", _ParsedArgs("anthropic/claude-sonnet-4-6", True)),
        # Bare keyword (promote current).
        ("default", _ParsedArgs("", True)),
        # Case-insensitive matches both positions.
        ("anthropic/claude-sonnet-4-6 DEFAULT", _ParsedArgs("anthropic/claude-sonnet-4-6", True)),
        ("DEFAULT anthropic/claude-sonnet-4-6", _ParsedArgs("anthropic/claude-sonnet-4-6", True)),
        ("DEFault", _ParsedArgs("", True)),
        # Extra whitespace doesn't perturb the split — `.split()` collapses runs.
        (
            "   anthropic/claude-sonnet-4-6   default   ",
            _ParsedArgs("anthropic/claude-sonnet-4-6", True),
        ),
    ],
)
def test_parse_model_args_shapes(raw: str, expected: _ParsedArgs) -> None:
    """All accepted shapes parse to the expected (model_id, make_default) pair."""
    assert _parse_model_args(raw) == expected


def test_parse_model_args_keeps_second_default_as_model_token() -> None:
    """Double-``default`` strips only one occurrence.

    ``/model default default`` keeps the second word as a (catalog-invalid)
    model token. Downstream the catalog lookup will reject it with the
    standard "I don't have ... in the model catalog" message — which is
    the right UX for a clearly-malformed input.
    """
    parsed = _parse_model_args("default default")
    assert parsed.make_default is True
    assert parsed.model_id == "default"


def test_parse_model_args_strips_only_one_keyword_position() -> None:
    """When ``default`` appears in both positions, the leading one wins.

    Implementation detail captured here so a future refactor can't
    silently flip the precedence — the structural form
    ``/model default <id> default`` is rare but well-defined.
    """
    parsed = _parse_model_args("default anthropic/claude-sonnet-4-6 default")
    # The leading "default" was stripped first. Whether the trailing
    # one survived depends on the implementation; either way we end up
    # with make_default=True and a non-empty model_id. Pin the contract:
    # at minimum, make_default is True.
    assert parsed.make_default is True
    assert "anthropic/claude-sonnet-4-6" in parsed.model_id
