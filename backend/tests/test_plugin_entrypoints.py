"""Tests for plugin Python entrypoint loading."""

from __future__ import annotations

import pytest

from app.plugins.entrypoints import load_entrypoint_callable
from app.plugins.errors import PluginRuntimeError

_NOT_CALLABLE = object()


def _sample_entrypoint() -> str:
    return "ok"


def test_load_entrypoint_callable_returns_nested_callable() -> None:
    target = load_entrypoint_callable(f"{__name__}:_sample_entrypoint")

    assert target() == "ok"


@pytest.mark.parametrize(
    "entrypoint",
    [
        "missing_separator",
        f"{__name__}:missing_attribute",
        f"{__name__}:_NOT_CALLABLE",
    ],
)
def test_load_entrypoint_callable_rejects_invalid_targets(entrypoint: str) -> None:
    with pytest.raises(PluginRuntimeError):
        load_entrypoint_callable(entrypoint)
