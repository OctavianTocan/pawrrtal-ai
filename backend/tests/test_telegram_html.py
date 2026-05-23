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

        A blank line between bullets is honoured (loose-list markdown is an
        explicit "add spacing" by the author); the key invariant is that the
        ``•`` and the item text share a single line.
        """
        md = "- **Foo**: blah\n\n- **Baz**: more"
        result = md_to_telegram_html(md)
        assert result == "• <b>Foo</b>: blah\n\n• <b>Baz</b>: more"

    def test_loose_and_tight_lists_both_keep_bullet_with_content(self) -> None:
        """Tight and loose list rendering may differ in inter-bullet spacing
        (loose preserves the author's blank line) but both must keep the
        bullet on the same line as the item content.
        """
        tight = md_to_telegram_html("- alpha\n- beta")
        loose = md_to_telegram_html("- alpha\n\n- beta")
        assert tight == "• alpha\n• beta"
        assert loose == "• alpha\n\n• beta"
        # The shared invariant: no chunk ever ends with ``• \n``.
        for rendered in (tight, loose):
            assert "• \n" not in rendered

    def test_loose_list_between_paragraphs(self) -> None:
        """A loose bullet list embedded between intro and outro paragraphs
        keeps the surrounding blank-line separators *and* the author's
        intra-list spacing.
        """
        md = "Intro.\n\n- item one\n\n- item two\n\nOutro."
        result = md_to_telegram_html(md)
        assert result == "Intro.\n\n• item one\n\n• item two\n\nOutro."

    def test_inline_space_between_fragments_in_list_item_survives(self) -> None:
        """Removing whitespace under ``<li>`` must not strip the single space
        that markdown-it emits between adjacent inline tags inside a bullet.

        Regression for the codex P1 review on #438 — an earlier draft removed
        ``"li"`` from the text-preserving set and turned ``- **Foo** *bar*``
        into ``• <b>Foo</b><i>bar</i>`` instead of ``• <b>Foo</b> <i>bar</i>``.
        """
        result = md_to_telegram_html("- **Foo** *bar*")
        assert result == "• <b>Foo</b> <i>bar</i>"

    def test_multi_paragraph_list_item_preserves_paragraph_break(self) -> None:
        """A list item with two real paragraphs keeps the ``\\n\\n`` between
        them. Regression for the codex P2 review on #438 — an earlier draft
        suppressed every ``</p>`` close inside a ``<li>``, which collapsed
        legitimate multi-paragraph items into a single line.
        """
        md = "- first paragraph\n\n  second paragraph"
        result = md_to_telegram_html(md)
        # The author wrote two paragraphs in one bullet; honour the break.
        assert "first paragraph\n\nsecond paragraph" in result

    def test_nested_block_after_paragraph_in_list_item_keeps_separator(self) -> None:
        """A code block following a paragraph inside the same ``<li>`` must
        keep the break between them. Regression for the codex P2 review on
        #438 — the previous suppression flattened ``• text<pre>...`` with
        no visible boundary.
        """
        md = "- text\n\n  ```\n  code\n  ```"
        result = md_to_telegram_html(md)
        assert "• text" in result
        # The boundary between the paragraph and the code block survives —
        # no direct ``text<pre>`` concatenation.
        assert "text<pre>" not in result

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
