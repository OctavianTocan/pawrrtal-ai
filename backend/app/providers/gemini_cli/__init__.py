"""Gemini CLI provider package.

Drives the locally-installed ``gemini`` binary via the Agent Client
Protocol (ACP, https://agentclientprotocol.com). External callers only
need the names re-exported below; everything else is package-internal.
"""

from .provider import (
    GEMINI_ACP_FLAG,
    GEMINI_BINARY_NAME,
    GeminiCliLLM,
    is_gemini_cli_available,
    render_history_prefix,
)

__all__ = [
    "GEMINI_ACP_FLAG",
    "GEMINI_BINARY_NAME",
    "GeminiCliLLM",
    "is_gemini_cli_available",
    "render_history_prefix",
]
