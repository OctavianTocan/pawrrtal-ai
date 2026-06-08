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
import re
from html.parser import HTMLParser

from markdown_it import MarkdownIt

_md = MarkdownIt()
_original_validate = _md.validateLink


def _custom_validate_link(url: str) -> bool:
    url_lower = url.strip().lower()
    if url_lower.startswith("file:"):
        return True
    return _original_validate(url)


_md.validateLink = _custom_validate_link  # type: ignore[method-assign]

_BLANK_LINE_RUN = re.compile(r"\n{3,}")


def _collapse_blank_lines(text: str) -> str:
    r"""Collapse runs of 3+ newlines down to ``\n\n``.

    Several dispatch helpers emit ``\n\n`` independently for adjacent
    constructs (``</p>`` close, ``</ul>`` close, heading close). When
    they stack — e.g. a loose-list's last ``</p>`` followed by the
    enclosing ``</ul>`` — the output picks up 3+ newlines, which
    Telegram renders as multiple blank lines and looks like rendering
    debris. Two newlines is the maximum vertical break the channel
    treats as meaningful; clamp the rest.
    """
    return _BLANK_LINE_RUN.sub("\n\n", text)


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
        "li",
        "p",
        "pre",
        "s",
        "strike",
        "strong",
        "u",
        *_HEADING_TAGS,
    }
)
# ``<li>`` IS in this set so single-space text nodes between inline
# fragments inside a bullet (``<strong>Foo</strong> <em>bar</em>``)
# survive. The pure-newline loose-list artifact (``<li>\n<p>…</p>\n``)
# is filtered separately in ``_is_inter_block_whitespace`` — see the
# special case there.


class _TelegramRenderer(HTMLParser):
    """Walk standard HTML from markdown-it-py and emit Telegram-safe HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf: list[str] = []
        self._open_tags: list[str] = []
        self._in_pre = False
        self._skip_stack: list[str] = []
        self._link_is_file: list[bool] = []

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
        r"""Return the accumulated Telegram-safe HTML string.

        Collapses runs of 3+ newlines down to ``\n\n``. The dispatch
        helpers emit ``\n\n`` independently for several constructs that
        can stack (``</p>`` close inside ``<li>`` plus a sibling
        ``</ul>`` close, ``</p>`` close before another block-level tag,
        etc.). Two newlines is the maximum vertical break Telegram
        renders meaningfully — beyond that the user sees walls of
        whitespace.
        """
        rendered = "".join(self._buf).strip()
        return _collapse_blank_lines(rendered)

    # ------------------------------------------------------------------
    # Dispatch helpers (keep individual methods under complexity limit)
    # ------------------------------------------------------------------

    def _is_inter_block_whitespace(self, data: str) -> bool:
        """Return true for markdown-it's formatting whitespace between blocks."""
        if self._in_pre or not data.isspace():
            return False
        # Loose-list artifact: markdown-it emits ``<li>\n<p>…</p>\n</li>``
        # when items are blank-line-separated. The ``\n`` chunks directly
        # under ``<li>`` (no inline tags open) are layout, not content;
        # keeping them puts the bullet on its own line above the text.
        # We narrowly target *pure-newline* whitespace so
        # the legitimate single space between ``<strong>Foo</strong>`` and
        # ``<em>bar</em>`` inside a bullet still survives.
        if (
            self._open_tags
            and self._open_tags[-1] == "li"
            and "\n" in data
            and " " not in data
            and "\t" not in data
        ):
            return True
        return not (set(self._open_tags) & _TEXT_PRESERVING_TAGS)

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
                if href.startswith("file://"):
                    self._link_is_file.append(True)
                    self._buf.append("<u>")
                else:
                    self._link_is_file.append(False)
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
                self._buf.append("\n\n")
            case "li":
                pass
            case "a":
                is_file = self._link_is_file.pop() if self._link_is_file else False
                if is_file:
                    self._buf.append("</u>")
                else:
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
        Falls back to the escaped *text* if conversion yields nothing.
    """
    raw_html = _md.render(text)
    renderer = _TelegramRenderer()
    renderer.feed(raw_html)
    converted = renderer.result()
    return converted if converted else _html.escape(text)
