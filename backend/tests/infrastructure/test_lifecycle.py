"""LifecycleRegistry: ordered startup/shutdown hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.infrastructure.lifecycle import LifecycleRegistry, default_registry, startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


def test_registry_records_hooks_in_order() -> None:
    """Hooks register with an order; iteration yields lowest-order first."""
    registry = LifecycleRegistry()

    @registry.startup(order=20)
    async def later(app: FastAPI) -> None:
        pass

    @registry.startup(order=10)
    async def earlier(app: FastAPI) -> None:
        pass

    ordered = registry.startup_hooks()
    assert [h.order for h in ordered] == [10, 20]
    assert [h.fn.__name__ for h in ordered] == ["earlier", "later"]


def test_shutdown_hooks_iterate_in_reverse_order() -> None:
    """Shutdown hooks iterate in reverse of their declared order."""
    registry = LifecycleRegistry()

    @registry.shutdown(order=10)
    async def first(app: FastAPI) -> None:
        pass

    @registry.shutdown(order=20)
    async def second(app: FastAPI) -> None:
        pass

    ordered = registry.shutdown_hooks()
    assert [h.order for h in ordered] == [20, 10]


def test_module_level_decorator_uses_default_registry() -> None:
    """The @startup_hook decorator registers on the module-level singleton."""
    initial_count = len(default_registry.startup_hooks())

    @startup_hook(order=999)
    async def example_hook(app: FastAPI) -> None:
        pass

    hooks = default_registry.startup_hooks()
    assert len(hooks) == initial_count + 1
    assert any(h.fn is example_hook for h in hooks)


@pytest.mark.asyncio
async def test_hook_fn_is_called_with_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registered hooks receive the FastAPI app instance when invoked."""
    registry = LifecycleRegistry()
    called_with: list[object] = []

    @registry.startup(order=1)
    async def capture(app: FastAPI) -> None:
        called_with.append(app)

    sentinel = object()
    await registry.startup_hooks()[0].fn(sentinel)  # type: ignore[arg-type]
    assert called_with == [sentinel]
