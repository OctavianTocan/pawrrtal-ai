"""Provider package — public surface for the AI provider abstraction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AILLM, ReasoningEffort, StreamEvent

if TYPE_CHECKING:
    from .catalog import default_model
    from .claude import ClaudeLLM, ClaudeLLMConfig
    from .factory import resolve_llm
    from .gemini_cli import GeminiCliLLM, is_gemini_cli_available
    from .xai import XaiLLM

__all__ = [
    "AILLM",
    "ClaudeLLM",
    "ClaudeLLMConfig",
    "GeminiCliLLM",
    "ReasoningEffort",
    "StreamEvent",
    "XaiLLM",
    "default_model",
    "is_gemini_cli_available",
    "resolve_llm",
]


def __getattr__(name: str) -> object:
    """Load provider implementations lazily.

    Importing ``app.providers.base`` should not load SDK-backed provider
    modules. The CLI and schemas use the base types frequently, and eager
    imports used to leak LiteLLM warnings into unrelated JSON commands.
    """
    if name == "default_model":
        from .catalog import default_model  # noqa: PLC0415

        return default_model
    if name == "resolve_llm":
        from .factory import resolve_llm  # noqa: PLC0415

        return resolve_llm
    if name in {"ClaudeLLM", "ClaudeLLMConfig"}:
        from .claude import ClaudeLLM, ClaudeLLMConfig  # noqa: PLC0415

        return {"ClaudeLLM": ClaudeLLM, "ClaudeLLMConfig": ClaudeLLMConfig}[name]
    if name in {"GeminiCliLLM", "is_gemini_cli_available"}:
        from .gemini_cli import GeminiCliLLM, is_gemini_cli_available  # noqa: PLC0415

        return {
            "GeminiCliLLM": GeminiCliLLM,
            "is_gemini_cli_available": is_gemini_cli_available,
        }[name]
    if name == "XaiLLM":
        from .xai import XaiLLM  # noqa: PLC0415

        return XaiLLM
    raise AttributeError(name)
