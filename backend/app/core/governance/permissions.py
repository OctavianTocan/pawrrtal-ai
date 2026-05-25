"""Provider-neutral ``can_use_tool`` gate.

Sits between the agent loop's tool dispatch (``loop.py:196``) and the
tool's ``execute`` callable. Every tool call — Claude or Gemini —
flows through one async function:

    decision = await check(tool_name, arguments, context)

A ``Deny`` decision short-circuits the call, emits a tool-error
result + a ``security_violation`` audit row, and lets the loop
continue with the model's next turn. An ``Allow`` decision falls
through to the existing executor.

What's checked (in order)
-------------------------
1. **Workspace tool allowlist** — when the workspace's
   ``.agent/protocols/permissions.md`` defines an explicit
   allowlist, respect it. Today the loader returns "no opinion"
   (permissive default); a Markdown→allowlist parser is future work.
2. **File-path boundary** — for tools whose arguments name a
   workspace file (``Read``, ``Write``, ``Edit``, ``MultiEdit``,
   ``workspace_read``, ``workspace_write``, ``workspace_list``,
   ``send_message``), delegate to the same resolver
   ``workspace_files`` uses so we share one source of truth.
3. **Bash directory boundary** — for ``Bash``/``bash``/``shell``
   tools, parse the command via :mod:`bash_boundary` and refuse
   any FS-modifying argument that escapes the workspace.

Composition
-----------
``build_default_permission_check`` returns the canonical bundle the
chat router wires into ``AgentLoopConfig``. Tests can build their
own bundle (e.g. workspace allowlist override) via
``compose_permission_checks(*funcs)`` so the gate stays a pure
function chain — no monkey-patching.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.governance.bash_boundary import check_bash_directory_boundary
from app.core.tools.workspace_files import (
    is_path_within_workspace,
    matches_forbidden_filename,
)

# Tool name sets we recognise for path / bash branches. Open sets so
# new tools that match the naming convention are gated automatically.
_FILE_TOOLS: frozenset[str] = frozenset(
    {
        "Write",
        "Edit",
        "MultiEdit",
        "Read",
        "create_file",
        "edit_file",
        "read_file",
        "workspace_read",
        "workspace_write",
        "workspace_list",
        "send_message",
    }
)
_BASH_TOOLS: frozenset[str] = frozenset({"Bash", "bash", "shell"})


@dataclass(frozen=True)
class PermissionContext:
    """Per-request context the gate consults.

    Built once per chat invocation by the chat router (and by the
    Telegram turn_stream wrapper) so each tool call sees the same
    user / workspace / surface metadata.

    ``workspace_root`` is the path the workspace tools are sandboxed
    to (also passed to ``make_workspace_tools``). The path-boundary
    check resolves arguments relative to this root.

    ``enabled_tools`` is the optional allowlist sourced from
    ``WorkspaceContext`` (PR 06). ``None`` means "no allowlist —
    accept any tool by name"; an empty set means "no tools are
    enabled".
    """

    user_id: str
    workspace_root: Path
    conversation_id: str
    surface: str
    enabled_tools: frozenset[str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PermissionDecision:
    """Outcome of one permission check.

    ``reason`` is human-readable and surfaces to the agent as the
    tool result + to the audit row's ``details``. ``violation_type``
    is a stable machine string the audit logger uses to bucket
    counters in the dashboard query.
    """

    allow: bool
    reason: str | None = None
    violation_type: str | None = None

    @classmethod
    def allowed(cls) -> PermissionDecision:
        """Singleton-style constructor for the common case."""
        return _ALLOW_SINGLETON

    @classmethod
    def deny(cls, reason: str, violation_type: str) -> PermissionDecision:
        """Build a denial with both a reason and a stable type tag."""
        return cls(allow=False, reason=reason, violation_type=violation_type)


_ALLOW_SINGLETON = PermissionDecision(allow=True)

PermissionCheckFn = Callable[
    [str, dict[str, Any], PermissionContext],
    Awaitable[PermissionDecision],
]


async def check_workspace_allowlist(
    tool_name: str,
    arguments: dict[str, Any],
    context: PermissionContext,
) -> PermissionDecision:
    """Reject tools not in the workspace's enabled-tools allowlist.

    No-op when ``context.enabled_tools is None`` so workspaces without
    an explicit allowlist accept every registered tool — the permissive
    default while a Markdown→allowlist parser for
    ``.agent/protocols/permissions.md`` is still future work.
    """
    _ = arguments  # not needed for an allowlist check
    if context.enabled_tools is None:
        return PermissionDecision.allowed()
    if tool_name in context.enabled_tools:
        return PermissionDecision.allowed()
    return PermissionDecision.deny(
        reason=(
            f"Tool '{tool_name}' is not enabled by this workspace's "
            "`.agent/protocols/permissions.md` allow list."
        ),
        violation_type="tool_disabled_by_workspace",
    )


# Keys we treat as "this argument names a workspace file". Matches what
# every file-shaped tool uses. Includes both the Claude SDK convention
# (``file_path``) and our tool factories' convention (``path`` /
# ``file``) so the gate covers both surfaces.
_PATH_ARGUMENT_KEYS: tuple[str, ...] = ("file_path", "path", "file")


async def check_file_path_boundary(
    tool_name: str,
    arguments: dict[str, Any],
    context: PermissionContext,
) -> PermissionDecision:
    """Reject file-tool calls whose path escapes the workspace.

    Catches three classes:

    * ``..`` traversal out of the workspace root.
    * Absolute paths that resolve outside the workspace.
    * Filenames in :data:`FORBIDDEN_FILENAMES` (``.env``, ``id_rsa``,
      …) or matching :data:`DANGEROUS_FILE_PATTERNS` (``*.pem``,
      ``*.key``, …) — even when those happen to live inside the
      workspace.
    """
    if tool_name not in _FILE_TOOLS:
        return PermissionDecision.allowed()

    raw_path: str | None = None
    for key in _PATH_ARGUMENT_KEYS:
        candidate = arguments.get(key)
        if isinstance(candidate, str) and candidate:
            raw_path = candidate
            break
    if raw_path is None:
        return PermissionDecision.allowed()

    if not is_path_within_workspace(raw_path, context.workspace_root):
        return PermissionDecision.deny(
            reason=(
                f"Tool '{tool_name}' targets '{raw_path}' which is "
                f"outside the workspace root '{context.workspace_root}'."
            ),
            violation_type="path_outside_workspace",
        )

    if matches_forbidden_filename(raw_path):
        return PermissionDecision.deny(
            reason=(
                f"Tool '{tool_name}' targets '{raw_path}' which is "
                "on the forbidden-filenames list (secrets / keys)."
            ),
            violation_type="forbidden_filename",
        )

    return PermissionDecision.allowed()


# Keys we look at for the command of a bash-shaped tool.
_BASH_COMMAND_KEYS: tuple[str, ...] = ("command", "cmd")


async def check_bash_command_boundary(
    tool_name: str,
    arguments: dict[str, Any],
    context: PermissionContext,
) -> PermissionDecision:
    """Reject bash invocations that step outside the workspace root."""
    if tool_name not in _BASH_TOOLS:
        return PermissionDecision.allowed()

    command: str | None = None
    for key in _BASH_COMMAND_KEYS:
        candidate = arguments.get(key)
        if isinstance(candidate, str) and candidate:
            command = candidate
            break
    if command is None:
        return PermissionDecision.allowed()

    allowed, reason = check_bash_directory_boundary(
        command,
        working_directory=context.workspace_root,
        approved_directory=context.workspace_root,
    )
    if allowed:
        return PermissionDecision.allowed()
    return PermissionDecision.deny(
        reason=reason or "Bash command escapes the workspace root.",
        violation_type="bash_directory_boundary",
    )


def compose_permission_checks(
    *checks: PermissionCheckFn,
) -> PermissionCheckFn:
    """Combine a stack of checks into one ``PermissionCheckFn``.

    Short-circuits on the first denial — the caller sees the most
    specific failure reason rather than a vague summary. All checks
    run in declaration order; ``Allow`` from every check yields
    ``Allow`` from the bundle.
    """

    async def composed(
        tool_name: str,
        arguments: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        for check in checks:
            decision = await check(tool_name, arguments, context)
            if not decision.allow:
                return decision
        return PermissionDecision.allowed()

    return composed


def build_default_permission_check() -> PermissionCheckFn:
    """Return the canonical permission-check bundle.

    Used by the chat router; tests / one-offs can call
    :func:`compose_permission_checks` with their own stack.
    """
    return compose_permission_checks(
        check_workspace_allowlist,
        check_file_path_boundary,
        check_bash_command_boundary,
    )


# Convenience surface for callers that don't want to remember which
# tool names are file-shaped vs bash-shaped. PR 03 audit-emission
# (``loop.py``) reads these to set the risk_level via the existing
# classifier helpers.
PermissionDecisionKind = Literal["allow", "deny"]


def decision_kind(decision: PermissionDecision) -> PermissionDecisionKind:
    """Stringify a decision for log lines / metrics."""
    return "allow" if decision.allow else "deny"


def iter_permission_modules() -> Iterable[str]:
    """Return the names of the modules a default bundle composes.

    Used by the ``/api/v1/audit/summary`` dashboard so the operator
    can see which checks fired vs which were configured. Kept as a
    sequence (not a tuple) so PR 06's workspace allowlist can append.
    """
    return [
        "workspace_allowlist",
        "file_path_boundary",
        "bash_command_boundary",
    ]


__all__ = [
    "PermissionCheckFn",
    "PermissionContext",
    "PermissionDecision",
    "build_default_permission_check",
    "check_bash_command_boundary",
    "check_file_path_boundary",
    "check_workspace_allowlist",
    "compose_permission_checks",
    "decision_kind",
    "iter_permission_modules",
]
