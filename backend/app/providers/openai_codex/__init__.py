"""Pawrrtal openai_codex provider package."""

from __future__ import annotations

import logging
from typing import Any

from ._vendor import ensure_openai_codex_available, get_openai_codex_module

logger = logging.getLogger(__name__)

# Public symbol names. Resolved lazily via __getattr__ so importing
# this package does not require a working Codex runtime. The Pawrrtal
# provider's stream(...) path is where we actually need the SDK; that
# path will raise loudly if the runtime is missing.
_SDK_TOP_LEVEL = (
    "Codex",
    "AsyncCodex",
    "AppServerConfig",
    "TextInput",
    "Input",
    "InputItem",
    "RunInput",
    "ImageInput",
    "LocalImageInput",
)
_SDK_DEEP = (
    "ReasoningEffort",
    "ReasoningSummary",
    "ApprovalMode",
    "SandboxMode",
    "Thread",
    "AsyncThread",
    "TurnHandle",
    "AsyncTurnHandle",
    "TurnResult",
    "AppServerError",
    "AppServerRpcError",
    "TransportClosedError",
    "RetryLimitExceededError",
)


def _resolve_sdk_symbol(name: str) -> Any:
    mod = get_openai_codex_module()
    val = getattr(mod, name, None)
    if val is not None:
        return val
    v2 = getattr(getattr(mod, "generated", None), "v2_all", None)
    if v2 is not None:
        return getattr(v2, name, None)
    return None


def __getattr__(name: str) -> Any:
    if name in _SDK_TOP_LEVEL or name in _SDK_DEEP:
        val = _resolve_sdk_symbol(name)
        if val is None:
            raise AttributeError(
                f"openai_codex SDK does not expose {name!r} "
                "in this version (vendored or installed)."
            )
        return val
    if name == "OpenAICodexProvider":
        from .provider import OpenAICodexProvider  # noqa: PLC0415

        return OpenAICodexProvider
    if name == "resolve_openai_codex_auth":
        from .auth import resolve_openai_codex_auth  # noqa: PLC0415

        return resolve_openai_codex_auth
    if name == "OpenAICodexAuthError":
        from .auth import OpenAICodexAuthError  # noqa: PLC0415

        return OpenAICodexAuthError
    raise AttributeError(name)


__all__ = [
    "AppServerConfig",
    "AppServerError",
    "AppServerRpcError",
    "ApprovalMode",
    "AsyncCodex",
    "AsyncThread",
    "AsyncTurnHandle",
    "Codex",
    "ImageInput",
    "Input",
    "InputItem",
    "LocalImageInput",
    "OpenAICodexAuthError",
    "OpenAICodexProvider",
    "ReasoningEffort",
    "ReasoningSummary",
    "RetryLimitExceededError",
    "RunInput",
    "SandboxMode",
    "TextInput",
    "Thread",
    "TransportClosedError",
    "TurnHandle",
    "TurnResult",
    "ensure_openai_codex_available",
    "get_openai_codex_module",
    "resolve_openai_codex_auth",
]
