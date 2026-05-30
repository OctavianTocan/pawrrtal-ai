"""Startup/shutdown hook registry for the FastAPI app lifecycle.

Each startup task lives in its own module under ``app/infrastructure/startup/``
and registers via the ``@startup_hook(order=N)`` decorator. Lower order =
earlier on startup. Shutdown hooks fire in reverse order via ``@shutdown_hook``.

The app's lifespan context manager iterates the registry; adding a new startup
task means one new file under ``startup/``, no edit to ``main.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

HookFn = Callable[["FastAPI"], Awaitable[None]]


@dataclass(frozen=True)
class Hook:
    """A single lifecycle hook with its execution order."""

    order: int
    fn: HookFn


@dataclass
class LifecycleRegistry:
    """Collects startup + shutdown hooks for ordered execution.

    Hooks are registered via the ``startup`` / ``shutdown`` decorators and
    retrieved in execution order via ``startup_hooks`` / ``shutdown_hooks``.
    """

    _startup: list[Hook] = field(default_factory=list)
    _shutdown: list[Hook] = field(default_factory=list)

    def startup(self, *, order: int) -> Callable[[HookFn], HookFn]:
        """Register a startup hook. Lower ``order`` runs first."""

        def decorator(fn: HookFn) -> HookFn:
            self._startup.append(Hook(order=order, fn=fn))
            return fn

        return decorator

    def shutdown(self, *, order: int) -> Callable[[HookFn], HookFn]:
        """Register a shutdown hook. Executed in reverse-``order``."""

        def decorator(fn: HookFn) -> HookFn:
            self._shutdown.append(Hook(order=order, fn=fn))
            return fn

        return decorator

    def startup_hooks(self) -> list[Hook]:
        """Return startup hooks in execution order (low → high)."""
        return sorted(self._startup, key=lambda h: h.order)

    def shutdown_hooks(self) -> list[Hook]:
        """Return shutdown hooks in execution order (high → low)."""
        return sorted(self._shutdown, key=lambda h: -h.order)


default_registry = LifecycleRegistry()


def startup_hook(*, order: int) -> Callable[[HookFn], HookFn]:
    """Module-level decorator using the default registry."""
    return default_registry.startup(order=order)


def shutdown_hook(*, order: int) -> Callable[[HookFn], HookFn]:
    """Module-level decorator using the default registry."""
    return default_registry.shutdown(order=order)
