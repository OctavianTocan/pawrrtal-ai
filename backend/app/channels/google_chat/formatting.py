"""Markdown → Google Chat text formatting.

Agent responses arrive as CommonMark, but Google Chat's message ``text``
field uses a *different* lightweight syntax and renders Markdown constructs
literally. The mismatch is why raw ``**bold**``, ``# headings`` and
``[text](url)`` show up in the chat. This module converts CommonMark to the
syntax Chat actually renders:

==================  ====================  =======================
Construct           CommonMark            Google Chat
==================  ====================  =======================
bold                ``**x**``             ``*x*``
italic              ``*x*`` / ``_x_``     ``_x_``
strikethrough       ``~~x~~``             ``~x~``
inline code         ``` `x` ```           ``` `x` ``` (same)
code block          ```` ```x``` ````     ```` ```x``` ```` (same)
link                ``[label](url)``      ``<url|label>``
heading             ``# H``               ``*H*`` (bold; Chat has none)
bullet list         ``- x`` / ``* x``     ``- x``
numbered list       ``1. x``              ``1. x``
==================  ====================  =======================

Mirrors :mod:`app.channels.telegram.html`: parse Markdown to HTML with
markdown-it-py, then walk the HTML and emit Chat-safe markup. Reference:
https://developers.google.com/workspace/chat/format-messages
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from markdown_it import MarkdownIt

# CommonMark + strikethrough (``~~x~~`` → ``<s>``). Strikethrough isn't in
# strict CommonMark; enabling just that rule avoids the gfm-like preset's
# linkify dependency.
_md = MarkdownIt().enable("strikethrough")
_BLANK_LINE_RUN = re.compile(r"\n{3,}")

# HTML inline tag → the Chat marker placed on both sides of the content.
_MARKERS: dict[str, str] = {
    "b": "*",
    "strong": "*",
    "i": "_",
    "em": "_",
    "s": "~",
    "del": "~",
    "strike": "~",
}
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_LIST_INDENT = "    "


@dataclass
class _ListFrame:
    """One open list level: its kind and the running item counter (for ``ol``)."""

    ordered: bool
    index: int = 0


class _ChatRenderer(HTMLParser):
    """Walk markdown-it HTML and emit Google Chat text markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._buf: list[str] = []
        self._in_pre = False
        self._lists: list[_ListFrame] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._dispatch_start(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        self._dispatch_end(tag)

    def handle_data(self, data: str) -> None:
        # Inside a code block the content is literal — keep it verbatim.
        if self._in_pre:
            self._buf.append(data)
            return
        # Drop markdown-it's inter-block layout whitespace (always contains a
        # newline); keep genuine inline spaces between formatted fragments.
        if data.strip() == "" and "\n" in data:
            return
        self._buf.append(data)

    def result(self) -> str:
        """Return the Chat-markup string, clamping blank-line runs to one."""
        return _BLANK_LINE_RUN.sub("\n\n", "".join(self._buf)).strip()

    def _dispatch_start(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        match tag:
            case t if t in _MARKERS:
                self._buf.append(_MARKERS[t])
            case t if t in _HEADINGS:
                self._buf.append("*")
            case "a":
                href = dict(attrs).get("href", "") or ""
                self._buf.append(f"<{href}|")
            case "pre":
                self._buf.append("```\n")
                self._in_pre = True
            case "code":
                if not self._in_pre:
                    self._buf.append("`")
            case "ul" | "ol":
                self._lists.append(_ListFrame(ordered=tag == "ol"))
            case "li":
                self._buf.append(self._bullet())
            case "br" | "hr":
                self._buf.append("\n")

    def _dispatch_end(self, tag: str) -> None:
        match tag:
            case t if t in _MARKERS:
                self._buf.append(_MARKERS[t])
            case t if t in _HEADINGS:
                self._buf.append("*\n\n")
            case "a":
                self._buf.append(">")
            case "pre":
                self._buf.append("\n```\n")
                self._in_pre = False
            case "code":
                if not self._in_pre:
                    self._buf.append("`")
            case "p":
                self._buf.append("\n\n")
            case "ul" | "ol":
                if self._lists:
                    self._lists.pop()
                self._buf.append("\n")

    def _bullet(self) -> str:
        """Return the newline + indent + marker prefix for a list item."""
        depth = max(len(self._lists), 1)
        indent = _LIST_INDENT * (depth - 1)
        frame = self._lists[-1] if self._lists else None
        if frame is not None and frame.ordered:
            frame.index += 1
            return f"\n{indent}{frame.index}. "
        return f"\n{indent}- "


def md_to_chat(text: str) -> str:
    """Convert CommonMark Markdown to Google Chat text markup.

    Falls back to the original *text* when conversion yields nothing (e.g. an
    empty or whitespace-only input), so a turn never blanks the message.
    """
    renderer = _ChatRenderer()
    renderer.feed(_md.render(text))
    converted = renderer.result()
    return converted if converted else text
