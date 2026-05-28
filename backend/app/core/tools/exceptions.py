"""Tool-domain exceptions: MCP + factory failures.

The external-MCP tool wrapper raises these and renders them to the
``[io_error] ...`` string contract the agent loop expects. Other tools
follow the same pattern — raise a typed exception, the wrapper translates.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.exceptions import DomainError


class ToolError(DomainError):
    """Root of tool-domain failures."""


class McpTimeoutError(ToolError):
    """MCP server didn't respond within the deadline."""


@dataclass
class McpAuthError(ToolError):
    """MCP server rejected auth.

    Attributes:
        status_code: HTTP status the server returned (usually 401 or 403).
    """

    status_code: int = 401


@dataclass
class McpServerError(ToolError):
    """MCP server returned a 5xx.

    Attributes:
        status_code: HTTP status the server returned.
    """

    status_code: int = 500


class McpProtocolError(ToolError):
    """MCP response didn't conform to the expected JSON-RPC shape."""
