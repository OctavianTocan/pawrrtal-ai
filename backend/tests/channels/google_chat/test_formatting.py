"""Google Chat channel — Markdown → Chat text-syntax conversion (formatting).

The agent emits CommonMark; Chat renders a different lightweight syntax
(``*bold*``, ``_italic_``, ``<url|label>``) and shows Markdown constructs like
``**bold**`` / ``# heading`` / ``[text](url)`` literally. These assert the
``md_to_chat`` converter bridges the two.
"""

from __future__ import annotations

from app.channels.google_chat.formatting import md_to_chat


def test_md_to_chat_bold_becomes_single_asterisk() -> None:
    assert md_to_chat("**bold**").strip() == "*bold*"


def test_md_to_chat_italic_becomes_underscore() -> None:
    assert md_to_chat("*italic*").strip() == "_italic_"


def test_md_to_chat_heading_becomes_bold() -> None:
    assert md_to_chat("# Title").strip() == "*Title*"


def test_md_to_chat_link_uses_angle_pipe() -> None:
    assert (
        md_to_chat("[Pawrrtal](https://pawrrtal.dev)").strip() == "<https://pawrrtal.dev|Pawrrtal>"
    )


def test_md_to_chat_inline_code_preserved() -> None:
    assert "`run`" in md_to_chat("Use `run` now")


def test_md_to_chat_strikethrough() -> None:
    assert md_to_chat("~~gone~~").strip() == "~gone~"


def test_md_to_chat_bulleted_list() -> None:
    out = md_to_chat("- one\n- two")
    assert "- one" in out
    assert "- two" in out


def test_md_to_chat_numbered_list_keeps_numbers() -> None:
    out = md_to_chat("1. first\n2. second")
    assert "1. first" in out
    assert "2. second" in out


def test_md_to_chat_code_block_fenced() -> None:
    out = md_to_chat("```\nx = 1\n```")
    assert "```" in out
    assert "x = 1" in out


def test_md_to_chat_plain_text_passthrough() -> None:
    assert md_to_chat("just text").strip() == "just text"
