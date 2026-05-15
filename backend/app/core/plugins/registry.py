"""Module-level plugin registry.

This is intentionally the simplest mechanism that solves the problem:
a list of :class:`Plugin` objects populated at import time by each
integration package, walked once per chat turn by
``build_agent_tools``.

There is no dynamic loading, no lifecycle, no per-plugin error
isolation beyond what Python's import system provides. A plugin that
raises at import surfaces immediately at server start — exactly when
we want to know.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.core.keys import resolve_api_key
from app.core.plugins.types import Plugin, ToolContext

logger = logging.getLogger(__name__)

# Internal mutable list. The public surface (``all_plugins``,
# ``register_plugin``) is what callers use; the list is hidden so a
# future refactor (e.g. plugin disable flags) can change the storage
# shape without breaking callers.
_REGISTRY: list[Plugin] = []


def register_plugin(plugin: Plugin) -> None:
    """Add ``plugin`` to the registry.

    Raises:
        ValueError: If a plugin with the same ``id`` is already
            registered. We refuse silent overwrites because they would
            mask real bugs — two integrations claiming the same id is
            never intentional.
    """
    for existing in _REGISTRY:
        if existing.id == plugin.id:
            raise ValueError(
                f"Plugin id '{plugin.id}' is already registered. "
                f"Each plugin must declare a unique id."
            )
    _REGISTRY.append(plugin)
    logger.info(
        "plugin_registered id=%s tools=%d env_keys=%d",
        plugin.id,
        len(plugin.tool_factories),
        len(plugin.env_keys),
    )


def all_plugins() -> tuple[Plugin, ...]:
    """Return every registered plugin in registration order.

    The return type is a tuple so callers can't accidentally mutate
    the registry. Order is preserved so plugin tools appear in a
    stable position in the agent's tool list (matters for
    snapshot-style tests).
    """
    return tuple(_REGISTRY)


def is_activated_by_env_keys(plugin: Plugin) -> Callable[[ToolContext], bool]:
    """Build the default activation predicate for ``plugin``.

    A plugin is activated when every ``required=True`` entry in its
    :attr:`Plugin.env_keys` resolves to a non-empty value for the
    active workspace. Plugins with no required env keys are always
    activated (they expose tools unconditionally).

    Plugins that need a more complex predicate override
    :attr:`Plugin.is_activated` directly; this helper is exposed so
    they can compose it with extra checks if they want the env-key
    behaviour as a baseline.
    """
    required_keys = tuple(spec.name for spec in plugin.env_keys if spec.required)

    def _predicate(ctx: ToolContext) -> bool:
        return all(resolve_api_key(ctx.workspace_id, key_name) for key_name in required_keys)

    return _predicate


def reset_for_tests() -> None:
    """Empty the registry. Exposed only for tests."""
    _REGISTRY.clear()
