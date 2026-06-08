"""Shared loader for Python plugin entrypoints."""

from __future__ import annotations

import importlib
from typing import Any

from app.plugins.errors import PluginRuntimeError


def load_entrypoint_callable(
    entrypoint: str,
    *,
    context: str = "plugin entrypoint",
) -> Any:
    """Load a callable declared as ``module:attribute`` from trusted plugin code.

    Entrypoints are imported directly, so manifests must be bundled or validated before loading.
    """
    module_name, separator, attribute_path = entrypoint.partition(":")
    if not separator or not module_name or not attribute_path:
        raise PluginRuntimeError(f"{context} must use 'module:attribute' syntax")
    try:
        target: Any = importlib.import_module(module_name)
        for attribute in attribute_path.split("."):
            target = getattr(target, attribute)
    except (ImportError, AttributeError) as exc:
        raise PluginRuntimeError(f"could not load {context} {entrypoint!r}") from exc
    if not callable(target):
        raise PluginRuntimeError(f"{context} {entrypoint!r} is not callable")
    return target
