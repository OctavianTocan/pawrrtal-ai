"""Cron scheduler — fires recurring agent tasks via the event bus.

Wraps APScheduler's ``AsyncIOScheduler`` with a Postgres-backed
``SQLAlchemyJobStore`` so jobs survive restarts.  Each fire publishes
a :class:`ScheduledEvent` to the global event bus; the AgentHandler
(PR 11b) subscribes there and runs the agent turn.

Lifespan:
* Construct + ``await start()`` in the FastAPI lifespan, after the
  event bus.
* ``await stop()`` in the lifespan teardown.

Both are no-ops when ``settings.scheduler_enabled`` is False.
"""

from app.core.scheduler.scheduler import JobScheduler

# Module-level accessor for the live :class:`JobScheduler`.  The
# FastAPI lifespan in ``backend/main.py`` registers the instance here
# alongside ``app.state.scheduler`` so contexts that don't have an
# HTTP ``Request`` (agent tools, background workers) can still reach
# it without an injection plumbing pass.  ``None`` when the scheduler
# is disabled via ``settings.scheduler_enabled``.
_active_scheduler: JobScheduler | None = None


def set_active_scheduler(scheduler: JobScheduler | None) -> None:
    """Register the live :class:`JobScheduler` for tool callers (#313)."""
    global _active_scheduler  # noqa: PLW0603 — lifespan singleton, set once per worker
    _active_scheduler = scheduler


def get_active_scheduler() -> JobScheduler | None:
    """Return the live :class:`JobScheduler`, or ``None`` when disabled."""
    return _active_scheduler


__all__ = ["JobScheduler", "get_active_scheduler", "set_active_scheduler"]
