"""Provider package — public surface for the AI provider abstraction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AILLM, ReasoningEffort, StreamEvent

if TYPE_CHECKING:
    from .catalog import first_catalog_model
    from .claude_code_pty import ClaudeCodePtyLLM, ClaudeCodePtyLLMConfig
    from .factory import resolve_llm
    from .xai import XaiLLM

__all__ = [
    "AILLM",
    "ClaudeCodePtyLLM",
    "ClaudeCodePtyLLMConfig",
    "ReasoningEffort",
    "StreamEvent",
    "XaiLLM",
    "first_catalog_model",
    "resolve_llm",
]


def __getattr__(name: str) -> object:
    """Load provider implementations lazily.

    Importing ``app.providers.base`` should not load SDK-backed provider
    modules. The CLI and schemas use the base types frequently, and eager
    imports used to leak LiteLLM warnings into unrelated JSON commands.
    """
    if name == "first_catalog_model":
        from .catalog import first_catalog_model  # noqa: PLC0415

        return first_catalog_model
    if name == "resolve_llm":
        from .factory import resolve_llm  # noqa: PLC0415

        return resolve_llm
    if name in {"ClaudeCodePtyLLM", "ClaudeCodePtyLLMConfig"}:
        from .claude_code_pty import ClaudeCodePtyLLM, ClaudeCodePtyLLMConfig  # noqa: PLC0415

        return {
            "ClaudeCodePtyLLM": ClaudeCodePtyLLM,
            "ClaudeCodePtyLLMConfig": ClaudeCodePtyLLMConfig,
        }[name]
    if name == "XaiLLM":
        from .xai import XaiLLM  # noqa: PLC0415

        return XaiLLM
    raise AttributeError(name)
