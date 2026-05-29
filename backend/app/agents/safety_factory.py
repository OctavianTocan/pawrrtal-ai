"""Build an :class:`AgentSafetyConfig` from application :class:`Settings`.

Kept in its own module (rather than inlined in ``chat.py``) so test code
and any future callers can build the same defaults without dragging in
the FastAPI router.
"""

from __future__ import annotations

from app.infrastructure.config import Settings

from .types import AgentSafetyConfig


def safety_from_settings(settings: Settings) -> AgentSafetyConfig:
    """Return an :class:`AgentSafetyConfig` reflecting current settings.

    Each ``agent_*`` field on :class:`Settings` maps 1:1 onto the
    matching :class:`AgentSafetyConfig` field.  When ``Settings`` is
    later widened (e.g. per-route overrides), this factory is the
    single place to thread that logic.
    """
    return AgentSafetyConfig(
        max_iterations=settings.agent_max_iterations,
        max_wall_clock_seconds=settings.agent_max_wall_clock_seconds,
        max_consecutive_llm_errors=settings.agent_max_consecutive_llm_errors,
        max_consecutive_tool_errors=settings.agent_max_consecutive_tool_errors,
        llm_retry_backoff_seconds=settings.agent_llm_retry_backoff_seconds,
    )
