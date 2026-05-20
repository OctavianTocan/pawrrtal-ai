"""Transient-error classification and exponential backoff for Claude.

Both helpers are pulled into their own module so
:mod:`app.core.providers.claude.provider` stays under the project's
500-line file budget.
"""

from __future__ import annotations

from app.core.config import settings as _settings

# Hard ceiling on per-retry sleep regardless of the configured backoff
# formula. Keeps a misconfigured ``claude_retry_max_delay_seconds`` from
# wedging the chat router for minutes.
_RETRY_SLEEP_CEILING_SECONDS = 30.0


def _is_retryable_cli_connection(error: BaseException) -> bool:
    """Decide whether a ``CLIConnectionError`` should trigger a retry.

    MCP-related connection errors are NOT retryable — they almost
    always indicate a configuration problem (a bridge server crashed,
    a tool wasn't mounted, …) and retrying just delays the visible
    failure.  Plain network / subprocess hiccups are retryable.
    """
    msg = str(error).lower()
    return "mcp" not in msg


def _retry_backoff_seconds(attempt: int) -> float:
    """Exponential backoff capped at :data:`_RETRY_SLEEP_CEILING_SECONDS`.

    ``attempt`` is 1-indexed (first failure is attempt 1, second is 2…)
    so a base of 1.0 with factor 2.0 produces 1, 2, 4, 8, … seconds.
    """
    base = float(_settings.claude_retry_base_delay_seconds)
    factor = float(_settings.claude_retry_backoff_factor)
    ceiling = float(_settings.claude_retry_max_delay_seconds)
    raw = base * (factor ** max(0, attempt - 1))
    return min(raw, ceiling, _RETRY_SLEEP_CEILING_SECONDS)
