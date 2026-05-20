"""Tool-call dispatch helpers for the agent loop.

Extracted from :mod:`app.core.agent_loop.loop` so the per-call observability
(args preview, duration, result length) and permission gating live in one
place and the outer loop stays inside the team's branch/statement budget.

All names beginning with an underscore are package-internal — call them
only from sibling modules inside :mod:`app.core.agent_loop` (see
``.claude/rules/clean-code/python-module-privacy.md``).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.agent_loop.types import AgentLoopConfig, AgentTool
from app.core.observability.workshop import tool_span

_log = logging.getLogger(__name__)

# Truncation budgets for tool-call trace logs. We log enough to identify a
# stuck loop ("model keeps calling tool X with args Y") without flooding the
# log with full tool payloads. Full bodies stay at DEBUG.
_LOG_ARGS_MAX_CHARS = 500
_LOG_RESULT_MAX_CHARS = 500


def _truncate_for_log(value: Any, max_chars: int) -> str:
    """Render a tool argument or result for logs, truncating long payloads.

    Args:
        value: The object to render. Dicts are rendered as ``repr`` so keys
            stay readable; strings pass through untouched.
        max_chars: Maximum number of characters in the returned string. The
            truncation marker counts toward the limit so the returned string
            is always at most ``max_chars`` characters long.

    Returns:
        A single-line, length-bounded representation suitable for an INFO
        log line. Newlines are collapsed so each trace stays on one line.
    """
    text = value if isinstance(value, str) else repr(value)
    text = text.replace("\n", " ").replace("\r", " ")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


async def _execute_and_log_tool_call(
    *,
    tc: Any,
    tool_map: dict[str, AgentTool],
    iteration: int,
    config: AgentLoopConfig,
) -> tuple[str, bool]:
    """Execute one tool call, emit ``TOOL_CALL_*`` traces, and return the result.

    Pulled out of the main loop so the per-call observability (args preview,
    duration, result length) lives in one place and the outer loop stays
    inside the team's branch/statement budget.

    Args:
        tc: The ``toolCall`` content block from the assistant message.
        tool_map: ``name → AgentTool`` lookup built once per loop iteration.
        iteration: 1-based loop iteration, included in the trace lines so
            stuck loops are easy to bucket by turn in the log.
        config: Loop config carrying the optional permission gate; checked
            before ``tool.execute`` so denied calls become surfaced errors
            instead of side-effecting executions.

    Returns:
        A ``(result_text, is_error)`` tuple. ``result_text`` is always
        non-empty so the caller can hand it straight to ``ToolResultEvent``
        and ``ToolResultMessage`` without further branching.
    """
    name: str = tc["name"]
    call_id: str = tc["tool_call_id"]
    arguments: dict[str, Any] = tc["arguments"]
    args_preview = _truncate_for_log(arguments, _LOG_ARGS_MAX_CHARS)
    _log.info(
        "TOOL_CALL_START iteration=%d name=%s tool_call_id=%s args=%s",
        iteration,
        name,
        call_id,
        args_preview,
    )

    # Workshop / OTel tool span — gives the live trace viewer a row
    # per call with the args + result + duration, scoped under the
    # surrounding ``pawrrtal.turn`` span.  No-op when telemetry off.
    with tool_span(name=name, tool_call_id=call_id, arguments=arguments) as ts:
        started_at = time.monotonic()
        result_text, is_error = await _dispatch_tool_call(
            tool_map=tool_map,
            name=name,
            call_id=call_id,
            arguments=arguments,
            config=config,
        )
        duration_ms = (time.monotonic() - started_at) * 1000.0
        ts.record_result(result_text, is_error=is_error)

    _log.info(
        "TOOL_CALL_RESULT iteration=%d name=%s tool_call_id=%s "
        "is_error=%s duration_ms=%.1f result_len=%d",
        iteration,
        name,
        call_id,
        is_error,
        duration_ms,
        len(result_text),
    )
    _log.debug(
        "TOOL_CALL_RESULT_BODY tool_call_id=%s body=%s",
        call_id,
        _truncate_for_log(result_text, _LOG_RESULT_MAX_CHARS),
    )
    return result_text, is_error


async def _dispatch_tool_call(
    *,
    tool_map: dict[str, AgentTool],
    name: str,
    call_id: str,
    arguments: dict[str, Any],
    config: AgentLoopConfig,
) -> tuple[str, bool]:
    """Resolve permission + execute one tool call, returning ``(result_text, is_error)``.

    Pulled out of :func:`_execute_and_log_tool_call` so the surrounding
    ``tool_span`` context-manager + log lines keep their own scope and
    the dispatcher stays inside the team's nesting budget.

    Args:
        tool_map: ``name → AgentTool`` lookup built once per loop iteration.
        name: Tool name from the assistant's ``toolCall`` block.
        call_id: Provider-stable id so a permission gate can echo it.
        arguments: Kwargs the model produced for the tool.
        config: Loop config carrying the optional permission gate.

    Returns:
        ``(result_text, is_error)`` where ``result_text`` is always
        non-empty.
    """
    tool = tool_map.get(name)
    if tool is None:
        return f"Tool '{name}' not found.", True
    permission_denial = await _check_permission_or_none(
        config=config,
        tool_name=name,
        arguments=arguments,
    )
    if permission_denial is not None:
        return permission_denial, True
    try:
        return await tool.execute(call_id, **arguments), False
    except Exception as exc:
        return f"Tool error: {exc}", True


async def _check_permission_or_none(
    *,
    config: AgentLoopConfig,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    """Run the configured permission gate, returning a denial message.

    Returns ``None`` when there's no gate or when the gate allows the
    call. Otherwise returns the denial reason as a string so the
    caller can surface it as the tool result. Also fires the optional
    ``permission_audit_sink`` (errors swallowed — audit failures must
    never break a turn).

    Kept as a module-level helper so the inner loop body in
    :func:`app.core.agent_loop.loop._run_loop` stays under the project's
    nesting budget.
    """
    if config.permission_check is None:
        return None
    try:
        decision = await config.permission_check(tool_name, arguments)
    except Exception as exc:
        # A crashed permission check is a configuration bug, not a
        # security signal — fail closed (deny) so a broken policy
        # doesn't silently allow tool use, but include the error so
        # the operator notices in logs.
        _log.exception("agent_loop: permission_check crashed; failing closed for %s", tool_name)
        return f"Tool '{tool_name}' denied: permission check error ({exc})."

    if decision.get("allow", False):
        return None

    reason = decision.get("reason") or "Tool call denied by permission policy."
    if config.permission_audit_sink is not None:
        try:
            await config.permission_audit_sink(tool_name, arguments, decision)
        except Exception:
            # Swallow audit failures — never break a turn over them.
            _log.exception("agent_loop: permission_audit_sink raised; ignoring")
    return reason
