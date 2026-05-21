"""Markdown → Telegram HTML conversion.

Telegram's HTML mode (``ParseMode.HTML``) supports a small subset of tags.
AI responses arrive as CommonMark Markdown. This module converts between them
so Telegram renders formatting instead of showing raw ``**`` and ``##`` markup.

Supported Telegram HTML tags (Bot API 7.3+):
  ``<b>``, ``<strong>``          bold
  ``<i>``, ``<em>``              italic
  ``<u>``                        underline
  ``<s>``, ``<del>``, ``<strike>`` strikethrough
  ``<code>``                     inline monospace
  ``<pre>``                      block monospace
  ``<a href="…">``               hyperlinks
  ``<blockquote>``               quote blocks

Unsupported structural tags are stripped; their *content* is preserved.
Block-level tags (``<p>``, ``<li>``, headings) are normalised to equivalent
Telegram markup (double newline, bullet prefix, bold, respectively).
"""

from __future__ import annotations

import html as _html
from html.parser import HTMLParser

from markdown_it import MarkdownIt

_md = MarkdownIt()

_INLINE_TAG_MAP: dict[str, str] = {
    "b": "b",
    "strong": "b",
    "i": "i",
    "em": "i",
    "u": "u",
    "s": "s",
    "del": "s",
    "strike": "s",
}

_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCK_PASSTHROUGH = frozenset({"p", "ul", "ol"})
_PASSTHROUGH_SKIP = frozenset({"html", "body", "head"})
_TEXT_PRESERVING_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "code",
        "del",
        "em",
        "i",
        "p",
        "pre",
        "s",
        "strike",
        "strong",
        "u",
        *_HEADING_TAGS,
    }
)
# ``<li>`` is intentionally **not** in this set.  markdown-it switches lists
# to *loose* mode when items are separated by a blank line and emits each
# item as ``<li>\n<p>…</p>\n</li>``.  Those ``\n`` chunks between ``<li>``
# and the inner ``<p>`` are layout artefacts, not content — keeping ``li``
# out of the set lets ``_is_inter_block_whitespace`` filter them so the
# bullet stays on the same line as the item text (issue #417).


class _TelegramRenderer(HTMLParser):
    """Walk standard HTML from markdown-it-py and emit Telegram-safe HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf: list[str] = []
        self._open_tags: list[str] = []
        self._in_pre = False
        self._skip_stack: list[str] = []

    # ------------------------------------------------------------------
    # HTMLParser overrides
    # ------------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _PASSTHROUGH_SKIP:
            return
        if self._skip_stack:
            self._skip_stack.append(tag)
            return
        if tag not in {"br", "hr"}:
            self._open_tags.append(tag)
        self._dispatch_start(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _PASSTHROUGH_SKIP:
            return
        if self._skip_stack:
            if self._skip_stack[-1] == tag:
                self._skip_stack.pop()
            return
        self._dispatch_end(tag)
        self._pop_open_tag(tag)

    def handle_data(self, data: str) -> None:
        if self._skip_stack or self._is_inter_block_whitespace(data):
            return
        self._buf.append(_html.escape(data))

    def result(self) -> str:
        """Return the accumulated Telegram-safe HTML string."""
        return "".join(self._buf).strip()

    # ------------------------------------------------------------------
    # Dispatch helpers (keep individual methods under complexity limit)
    # ------------------------------------------------------------------

    def _is_inter_block_whitespace(self, data: str) -> bool:
        """Return true for markdown-it's formatting whitespace between blocks."""
        is_container_whitespace = data.isspace() and not (
            set(self._open_tags) & _TEXT_PRESERVING_TAGS
        )
        return not self._in_pre and is_container_whitespace

    def _pop_open_tag(self, tag: str) -> None:
        if self._open_tags and self._open_tags[-1] == tag:
            self._open_tags.pop()

    def _dispatch_start(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # `match` keeps the dispatch flat (depth-1 in the AST nesting lint)
        # while preserving the readable "tag → markup" table shape that an
        # if/elif chain expressed. Order of cases mirrors the original.
        match tag:
            case t if t in _INLINE_TAG_MAP:
                self._buf.append(f"<{_INLINE_TAG_MAP[t]}>")
            case t if t in _HEADING_TAGS:
                self._buf.append("<b>")
            case t if t in _BLOCK_PASSTHROUGH:
                pass
            case "li":
                self._start_list_item()
            case "hr" | "br":
                self._buf.append("\n")
            case "a":
                href = _html.escape(dict(attrs).get("href", "") or "")
                self._buf.append(f'<a href="{href}">')
            case "blockquote":
                self._buf.append("<blockquote>")
            case "pre":
                self._buf.append("<pre>")
                self._in_pre = True
            case "code":
                self._start_code(attrs)
            case _:
                self._skip_stack.append(tag)

    def _start_code(self, attrs: list[tuple[str, str | None]]) -> None:
        if not self._in_pre:
            self._buf.append("<code>")
            return
        lang = dict(attrs).get("class", "") or ""
        tag_text = f'<code class="{_html.escape(lang)}">' if lang else "<code>"
        self._buf.append(tag_text)

    def _start_list_item(self) -> None:
        if not self._buf or self._buf[-1].endswith("\n\n"):
            self._buf.append("• ")
            return
        self._buf.append("\n• ")

    def _dispatch_end(self, tag: str) -> None:
        # See ``_dispatch_start`` — same shape, same reason for ``match``.
        match tag:
            case t if t in _HEADING_TAGS:
                self._buf.append("</b>\n\n")
            case "ul" | "ol":
                self._buf.append("\n\n")
            case "p":
                # Inside a loose-list ``<li>`` the surrounding ``<p>`` is a
                # markdown-it artefact, not a real paragraph break — emitting
                # ``\n\n`` here would push the bullet onto its own line (#417).
                # Top-level paragraphs still get the blank-line separator.
                if "li" not in self._open_tags:
                    self._buf.append("\n\n")
            case "li":
                pass
            case "a":
                self._buf.append("</a>")
            case "blockquote":
                self._buf.append("</blockquote>")
            case "pre":
                self._buf.append("</pre>\n")
                self._in_pre = False
            case "code":
                self._buf.append("</code>")
            case t if t in _INLINE_TAG_MAP:
                self._buf.append(f"</{_INLINE_TAG_MAP[t]}>")


def md_to_telegram_html(text: str) -> str:
    """Convert CommonMark Markdown to Telegram HTML (``ParseMode.HTML``).

    Args:
        text: AI-generated Markdown string (may be complete or mid-stream).

    Returns:
        HTML string safe to pass to Telegram with ``ParseMode.HTML``.
        Falls back to the original *text* if conversion yields nothing.
    """
    raw_html = _md.render(text)
    renderer = _TelegramRenderer()
    renderer.feed(raw_html)
    converted = renderer.result()
    return converted if converted else text
