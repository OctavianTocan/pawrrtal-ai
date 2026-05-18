"""Startup-time housekeeping for the subagent system.

Called once from the FastAPI lifespan in :mod:`main` after the DB
tables exist.  Catches subagents whose host process died mid-run — the
durable row stayed at ``status="running"`` because the runner's
finalize step never ran — and marks them ``failed`` with a stable
error string so the UI and the daily cap don't see a phantom live
subagent forever.

Documented v1 limitation: subagents do not survive process restarts.
A proper durable runner (Arq / Dramatiq / similar) is a v2 concern;
v1 trades durability for the simplest possible runner that fits the
existing FastAPI lifespan.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import update

from app.models import Subagent

logger = logging.getLogger(__name__)


#: Stable error string written to ``subagents.error`` for rows the
#: reaper rescues.  Audit queries and the frontend's failure UI can
#: match on this exact value.
REAPER_ERROR_REASON: str = "process restarted before completion"


async def reap_orphaned_subagents(session_maker) -> int:
    """Mark every ``running`` row as ``failed`` with the reaper reason.

    Returns the count of rows updated so the lifespan hook can log
    whether any reaper work was actually needed.  Safe to call on a
    clean boot — the UPDATE matches zero rows and the function
    returns 0.

    ``session_maker`` is the project's ``async_session_maker`` (a
    callable that returns an async context manager yielding an
    ``AsyncSession``).  Passed in rather than imported so the reaper
    is trivially testable with a fixture session maker.
    """
    completed_at = datetime.now(UTC).replace(tzinfo=None)
    async with session_maker() as session:
        result = await session.execute(
            update(Subagent)
            .where(Subagent.status == "running")
            .values(
                status="failed",
                error=REAPER_ERROR_REASON,
                completed_at=completed_at,
            )
        )
        await session.commit()
        rowcount = result.rowcount or 0
    if rowcount > 0:
        logger.warning(
            "SUBAGENT_REAPER_RESCUED count=%d reason=%s",
            rowcount,
            REAPER_ERROR_REASON,
        )
    else:
        logger.info("SUBAGENT_REAPER_CLEAN no orphaned running rows")
    return int(rowcount)


__all__ = ["REAPER_ERROR_REASON", "reap_orphaned_subagents"]
