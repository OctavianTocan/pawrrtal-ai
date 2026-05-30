"""Centralised tool-error model.

Tools the agent loop calls have so far signalled failure by returning a
free-form ``"Error: ..."`` string.  That works but it's hostile to callers
who want to react to specific failures (the upcoming permissions gate, the
chat surface that wants to render different banners for ``NOT_FOUND`` vs
``OUT_OF_ROOT``, dashboards that aggregate by failure type, etc.).

This module introduces:

  - :class:`ToolErrorCode` — a closed enum of recognised failure codes.
  - :class:`ToolError` — a typed exception carrying a code and a message.

Tool bodies raise :class:`ToolError` when something goes wrong; the
workspace-tool wrapper (and any future tool wrapper) catches it and renders
a stable ``"[<code>] <message>"`` string for the model.  Programmatic
callers — tests, the permissions gate, the chat router — can match on
the code without parsing a sentence.

Why a flat enum instead of an exception hierarchy: every failure mode here
is a leaf condition the model is supposed to read and adjust to, not a
class hierarchy with shared behaviour.  An enum keeps the surface honest
and easy to extend (one entry per failure mode, no ambiguous catches).
"""

from __future__ import annotations

from enum import StrEnum


class ToolErrorCode(StrEnum):
    """Recognised tool failure modes.

    Codes are stable strings: tests, telemetry, and the chat surface key
    on these values, so renaming one is a breaking change.
    """

    INVALID_PATH = "invalid_path"
    """Path argument was missing, malformed, or unresolvable."""

    OUT_OF_ROOT = "out_of_root"
    """Path resolved to a location outside the workspace root."""

    NOT_FOUND = "not_found"
    """Target did not exist."""

    WRONG_KIND = "wrong_kind"
    """Target existed but had the wrong kind (file vs directory)."""

    BINARY_FILE = "binary_file"
    """Tried to read a binary file as text."""

    IO_ERROR = "io_error"
    """Underlying ``OSError`` from the filesystem."""

    PERMISSION_DENIED = "permission_denied"
    """Reserved for the upcoming permissions gate (PR follow-up)."""


class ToolError(Exception):
    """Typed failure raised by tool bodies.

    Attributes:
        code: A :class:`ToolErrorCode` for programmatic matching.
        message: Human-readable detail for the model and the UI.
    """

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def render(self) -> str:
        """Format the error for the model.

        The ``[code]`` prefix lets a future system-prompt snippet teach the
        agent how to react (e.g. "if you see [out_of_root], stay inside the
        workspace") without parsing free text.
        """
        return f"[{self.code.value}] {self.message}"
