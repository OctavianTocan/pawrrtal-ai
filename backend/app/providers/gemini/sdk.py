"""Lazy google-genai SDK access.

The google-genai package defines an aiohttp ``ClientSession`` subclass at
import time. Newer aiohttp versions emit a ``DeprecationWarning`` for that
third-party class definition before Pawrrtal has made any Gemini call. Keep
that import-time warning contained at the SDK boundary so unrelated provider
imports and tests stay warning-clean.
"""

from __future__ import annotations

import warnings
from functools import cache
from types import ModuleType
from typing import TYPE_CHECKING, Any, Literal

_CLIENT_SESSION_WARNING = "Inheritance class AiohttpClientSession from ClientSession is discouraged"


@cache
def _load_sdk() -> tuple[ModuleType, ModuleType]:
    """Import and return ``(google.genai, google.genai.types)`` once."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=_CLIENT_SESSION_WARNING,
            category=DeprecationWarning,
        )
        from google import genai as genai_module  # noqa: PLC0415
        from google.genai import types as types_module  # noqa: PLC0415

    return genai_module, types_module


class _LazySdkModule:
    """Small proxy that imports the SDK only when an attribute is used."""

    def __init__(self, kind: Literal["genai", "types"]) -> None:
        self._kind = kind
        self._overrides: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._target(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        self._overrides[name] = value

    def __delattr__(self, name: str) -> None:
        if name in self._overrides:
            del self._overrides[name]
            return
        raise AttributeError(name)

    def _target(self) -> ModuleType:
        genai_module, types_module = _load_sdk()
        if self._kind == "genai":
            return genai_module
        return types_module


if TYPE_CHECKING:
    from google import genai
    from google.genai import types as gtypes
else:
    genai = _LazySdkModule("genai")
    gtypes = _LazySdkModule("types")

__all__ = ["genai", "gtypes"]
