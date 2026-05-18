"""``now`` AgentTool — current wall-clock time, no network required.

Companion to the system-prompt time block in
:mod:`app.core.runtime_context`. The block is fired every turn so the
model is never blind to the date, but multi-step turns can span minutes
and the model might want to double-check during a long run. This tool
gives it a zero-cost way to re-query the clock without rebuilding the
system prompt or burning iterations on ``exa_search`` for "current
time in <city>".

Threat model
~~~~~~~~~~~~
Pure stdlib (``datetime`` + ``zoneinfo``). No network, no filesystem, no
sandbox concern. Always-available, never gated.

Closes #294.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.agent_loop.types import AgentTool

# Re-export the TASKS.md tools (#311 v1) through this module so
# ``agent_tools.py`` can import them off ``now`` and stay under
# sentrux's ``no_god_files`` fan-out ceiling. The aggregation is
# purely organisational; the implementations live in ``tasks_md.py``.
from app.core.tools.cron_tools import (  # noqa: F401
    make_cron_create_tool,
    make_cron_delete_tool,
    make_cron_list_tool,
)
from app.core.tools.display import make_tool_display
from app.core.tools.tasks_md import (  # noqa: F401
    make_add_task_tool,
    make_complete_task_tool,
    make_list_tasks_tool,
)

log = logging.getLogger(__name__)


def _format_now(tz: ZoneInfo, fallback_label: str | None = None) -> str:
    """Return a multi-line Markdown answer describing the current time.

    Args:
        tz: The local timezone to render alongside UTC.
        fallback_label: Optional label to surface in the response when
            the caller asked for a tz that didn't resolve and we fell
            back to UTC. Lets the model know to suggest a correction.

    Returns:
        A Markdown string with ISO-8601 UTC, local time, day-of-week,
        and the IANA timezone name. Always non-empty.
    """
    utc = _dt.datetime.now(_dt.UTC)
    local = utc.astimezone(tz)
    lines = [
        f"- UTC now: {utc.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"- Local time: {local.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- Timezone: {tz.key}",
        f"- Day of week: {local.strftime('%A')}",
    ]
    if fallback_label:
        lines.append(f"- Note: '{fallback_label}' is not a known IANA timezone — fell back to UTC.")
    return "\n".join(lines)


def make_now_tool(*, default_timezone: str = "UTC") -> AgentTool:
    """Return the ``now`` AgentTool.

    Args:
        default_timezone: IANA timezone applied when the model calls
            ``now`` without a ``tz`` argument. Sourced from the user's
            profile when available; otherwise UTC.

    Returns:
        An :class:`AgentTool` with a single optional ``tz`` parameter.
    """

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        requested = kwargs.get("tz")
        # Coerce non-string ``tz`` values to ``None`` rather than erroring
        # — bad input shouldn't make the model burn a retry to check the
        # time. We always return a useful answer.
        if not isinstance(requested, str) or not requested.strip():
            requested = None
        effective = requested or default_timezone
        try:
            zone = ZoneInfo(effective)
        except ZoneInfoNotFoundError:
            log.info("now() received unknown timezone '%s'; falling back to UTC.", effective)
            return _format_now(ZoneInfo("UTC"), fallback_label=effective)
        return _format_now(zone)

    return AgentTool(
        name="now",
        description=(
            "Return the current wall-clock time as ISO-8601 UTC plus the "
            "user's local time, IANA timezone, and day of week. Use this "
            "when you need to reason about 'today' / 'yesterday', schedule "
            "future actions, or double-check the time mid-turn — it costs "
            "nothing and is always more authoritative than a web search."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tz": {
                    "type": "string",
                    "description": (
                        "Optional IANA timezone name (e.g. 'Europe/Madrid', "
                        "'America/Los_Angeles'). Defaults to the user's "
                        "configured timezone, or UTC when none is set."
                    ),
                }
            },
            "required": [],
        },
        execute=execute,
        display=make_tool_display(
            icon="🕒",
            label="Check the time",
            present=lambda args: (
                f"🕒 Checking the time ({args.get('tz')})"
                if args.get("tz")
                else "🕒 Checking the time"
            ),
            compact=lambda args: f"now({args.get('tz')})" if args.get("tz") else "now()",
        ),
    )
