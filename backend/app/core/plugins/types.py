"""Type definitions for the plugin registry.

A plugin contributes :class:`AgentTool` instances on demand. The host
hands every tool factory a :class:`ToolContext` carrying the call-time
fields the factory needs to bind correctly: which workspace is active,
where on disk it lives, who the authenticated user is, and how the
agent should deliver messages back if applicable.

This module is deliberately small: the registry is a list of
:class:`Plugin` objects, ``build_agent_tools`` walks it, and each
factory is responsible for its own JSON-Schema and execute callable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.agent_loop.types import AgentTool
    from app.core.tools.send_message import SendFn


@dataclass(frozen=True)
class EnvKeySpec:
    """One workspace-scoped environment key declared by a plugin.

    Plugins use these to teach the host which keys belong to them —
    today this is informational (the central ``OVERRIDABLE_KEYS``
    allowlist in :mod:`app.core.keys` is still the source of truth);
    once the settings UI auto-renders rows from the registry, the
    ``label`` and ``help_url`` fields become user-visible.

    Attributes:
        name: The env-var name as stored in the workspace ``.env``
            (e.g. ``"NOTION_API_KEY"``). Must match the corresponding
            entry in :data:`app.core.keys.OVERRIDABLE_KEYS`.
        label: Short human-readable label for the Settings UI.
        help_url: Optional link to documentation explaining how to
            obtain a value for this key (e.g. Notion's integration
            page). ``None`` if the key is self-explanatory.
        required: When ``True``, the plugin's default activation
            predicate refuses to expose tools unless this key resolves
            to a non-empty value. When ``False``, the plugin handles
            its own absence (e.g. emits a friendlier error at execute
            time). Default ``True``.
    """

    name: str
    label: str
    help_url: str | None = None
    required: bool = True


@dataclass(frozen=True)
class ToolContext:
    """The per-call binding passed into every plugin tool factory.

    Mirrors the keyword arguments the chat router already collects
    when composing the tool list, so adding a plugin never requires
    touching the router again.

    Attributes:
        workspace_id: The active workspace UUID. Plugins resolve env
            keys via :func:`app.core.keys.resolve_api_key` against this
            workspace.
        workspace_root: Absolute filesystem path to the workspace
            directory (the same path passed to core workspace tools).
            Plugins may read or write under this root with the same
            invariants as core tools (no traversal, scoped writes).
        user_id: Authenticated user UUID. Useful for audit logging
            and for legacy lookups that still key by user.
        send_fn: Optional channel delivery callback. When supplied,
            plugins MAY register tools that proactively push messages
            back to the user mid-turn. When ``None``, such tools should
            be omitted from the factory's return value.
    """

    workspace_id: uuid.UUID
    workspace_root: Path
    user_id: uuid.UUID
    send_fn: SendFn | None = None


ToolFactory = Callable[[ToolContext], "AgentTool"]
"""A function that produces one ``AgentTool`` bound to a ``ToolContext``."""


@dataclass(frozen=True)
class Plugin:
    """One registered integration.

    Attributes:
        id: Stable machine-readable identifier (e.g. ``"notion"``).
            Must be unique across the registry; the loader rejects
            duplicates.
        name: Short human-readable label shown in the Settings UI.
        description: One-sentence summary of what the integration does.
        env_keys: Tuple of env keys the plugin declares ownership of.
            By default, the activation predicate requires every
            ``required=True`` key to resolve in the current workspace
            before any of this plugin's tools are exposed to the agent.
        tool_factories: Tuple of factories that produce the plugin's
            tools when called with a :class:`ToolContext`. Order is
            preserved in the final tool list (after all core tools).
        is_activated: Optional override for the activation predicate.
            Default behaviour returns ``True`` when every required
            ``env_key`` resolves to a non-empty value for the active
            workspace.
    """

    id: str
    name: str
    description: str
    env_keys: tuple[EnvKeySpec, ...] = field(default_factory=tuple)
    tool_factories: tuple[ToolFactory, ...] = field(default_factory=tuple)
    is_activated: Callable[[ToolContext], bool] | None = None
