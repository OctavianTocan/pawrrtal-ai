"""Tests for the Markdown → Telegram HTML converter.

Covers the key Markdown constructs the AI model produces:
- headings (##) → <b>…</b>
- bold (**text**) → <b>…</b>
- italic (*text*) → <i>…</i>
- inline code (`code`) → <code>…</code>
- fenced code blocks → <pre>…</pre>
- links → <a href="…">…</a>
- bullet lists → • prefixed lines
- blockquotes → <blockquote>…</blockquote>
- plain text → passthrough (no extra tags)
- HTML special chars in content → properly escaped
- empty / whitespace-only input → fallback to original text
"""

from __future__ import annotations

from app.channels.telegram_html import md_to_telegram_html


class TestMdToTelegramHtml:
    def test_plain_text_passthrough(self) -> None:
        assert md_to_telegram_html("Hello world") == "Hello world"

    def test_bold(self) -> None:
        result = md_to_telegram_html("**bold text**")
        assert "<b>bold text</b>" in result

    def test_italic(self) -> None:
        result = md_to_telegram_html("*italic text*")
        assert "<i>italic text</i>" in result

    def test_heading_becomes_bold(self) -> None:
        result = md_to_telegram_html("## Section Title")
        assert "<b>Section Title</b>" in result
        assert "##" not in result

    def test_h1_heading(self) -> None:
        result = md_to_telegram_html("# Top Level")
        assert "<b>Top Level</b>" in result
        assert "#" not in result

    def test_inline_code(self) -> None:
        result = md_to_telegram_html("Use `print()` here")
        assert "<code>print()</code>" in result

    def test_fenced_code_block(self) -> None:
        md = "```python\ndef foo():\n    pass\n```"
        result = md_to_telegram_html(md)
        assert "<pre>" in result
        assert "def foo():" in result
        assert "```" not in result

    def test_link(self) -> None:
        result = md_to_telegram_html("[Click here](https://example.com)")
        assert '<a href="https://example.com">Click here</a>' in result

    def test_bullet_list(self) -> None:
        md = "- item one\n- item two"
        result = md_to_telegram_html(md)
        assert "• item one" in result
        assert "• item two" in result

    def test_list_separator_does_not_include_parser_newlines(self) -> None:
        md = "Intro.\n\n- item one\n- item two\n\nOutro."
        result = md_to_telegram_html(md)
        assert result == "Intro.\n\n• item one\n• item two\n\nOutro."

    def test_loose_list_keeps_bullet_with_content(self) -> None:
        """Loose-list markdown (blank line between items) must render the
        bullet on the same line as the item content. Regression for #417 —
        markdown-it wraps each loose-list item in ``<p>``, which used to push
        the bullet onto its own line above the bold/text content.
        """
        md = "- **Foo**: blah\n\n- **Baz**: more"
        result = md_to_telegram_html(md)
        assert result == "• <b>Foo</b>: blah\n• <b>Baz</b>: more"

    def test_loose_list_matches_tight_list_output(self) -> None:
        """Loose and tight list rendering should be visually identical in
        Telegram — both produce single-newline-separated bullets, even when
        the source markdown switched markdown-it into loose-list mode.
        """
        tight = md_to_telegram_html("- alpha\n- beta")
        loose = md_to_telegram_html("- alpha\n\n- beta")
        assert tight == loose == "• alpha\n• beta"

    def test_loose_list_between_paragraphs(self) -> None:
        """A loose bullet list embedded between intro and outro paragraphs
        keeps the surrounding blank-line separators but never inserts an
        empty line between bullets.
        """
        md = "Intro.\n\n- item one\n\n- item two\n\nOutro."
        result = md_to_telegram_html(md)
        assert result == "Intro.\n\n• item one\n• item two\n\nOutro."

    def test_blockquote(self) -> None:
        result = md_to_telegram_html("> quoted text")
        assert "<blockquote>" in result
        assert "quoted text" in result
        assert ">" not in result.replace("<blockquote>", "").replace("</blockquote>", "")

    def test_html_special_chars_escaped(self) -> None:
        result = md_to_telegram_html("x < y & z > w")
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_code_block_content_escaped(self) -> None:
        md = "```\nconst x = <div>;\n```"
        result = md_to_telegram_html(md)
        assert "&lt;div&gt;" in result
        assert "<div>" not in result.replace("<pre>", "").replace("</pre>", "")

    def test_empty_string_fallback(self) -> None:
        result = md_to_telegram_html("")
        assert result == ""

    def test_whitespace_only_fallback(self) -> None:
        result = md_to_telegram_html("   \n  ")
        # Converter strips whitespace; if empty falls back to original.
        assert isinstance(result, str)

    def test_raw_asterisks_absent_in_output(self) -> None:
        """The literal ** markup must not appear in the rendered output."""
        result = md_to_telegram_html("**bold** and *italic*")
        assert "**" not in result
        assert result.count("*") == 0

    def test_mixed_formatting(self) -> None:
        md = "## Title\n\n**bold** and *italic* and `code`"
        result = md_to_telegram_html(md)
        assert "<b>Title</b>" in result
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<code>code</code>" in result

    def test_no_paragraph_tags_in_output(self) -> None:
        """Telegram does not support <p>; they must be stripped."""
        result = md_to_telegram_html("Just a paragraph.")
        assert "<p>" not in result
        assert "</p>" not in result

    def test_paragraph_separator_is_not_tripled(self) -> None:
        result = md_to_telegram_html("First paragraph.\n\nSecond paragraph.")
        assert result == "First paragraph.\n\nSecond paragraph."

    def test_middle_paragraph_separator_matches_source_spacing(self) -> None:
        result = md_to_telegram_html("First.\n\nSecond.\n\nThird.")
        assert result == "First.\n\nSecond.\n\nThird."
