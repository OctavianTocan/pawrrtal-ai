"""ORM model for the subagent registry.

Lives in its own module — not inside ``app.models`` — to keep the main
models file under the project's 500-line budget, mirroring the
:mod:`app.governance_models` split.  Re-exported from
:mod:`app.models` at the bottom of that file so existing
``from app.models import Subagent`` imports keep working.

The subagent system itself (persona loader, registry CRUD, background
runner, the five tools) lives under ``app.core.subagents`` and
``app.crud.subagent``.  This file is **only** the SQLAlchemy model
plus its tightly-coupled type aliases — no business logic.

Lifecycle (durable state):

    running ───┬───▶ succeeded
               ├───▶ failed
               └───▶ cancelled

Only ``running`` rows are live in the in-process registry that PR 3
adds.  The terminal states are write-once: the row is patched with
``result`` (or ``error``) and ``completed_at``, never reopened.
"""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from .db_base import Base

# ---------------------------------------------------------------------------
# Status — string column with a strict Python-side type
# ---------------------------------------------------------------------------

#: Width of the ``status`` column.  16 chars is comfortably more than any
#: name in :data:`SUBAGENT_STATUSES` so future status additions don't
#: force an Alembic alter.
_STATUS_COL_LEN: int = 16

#: Width of the ``persona_name`` column — matches the regex cap on
#: ``_PersonaSpec.name`` (``max_length=64``).
_PERSONA_NAME_COL_LEN: int = 64

#: Width of the ``handle`` column.  Handles look like ``researcher#a3f``;
#: 80 chars covers persona names up to 64 plus the suffix and a margin
#: in case we extend the suffix encoding later.
_HANDLE_COL_LEN: int = 80

#: Width of the optional ``label`` column the parent can attach for
#: human-friendly identification in the UI ("market scan for X").
_LABEL_COL_LEN: int = 200

SubagentStatus = Literal["running", "succeeded", "failed", "cancelled"]
"""Discriminated set of statuses a subagent row can hold.

Kept narrow on purpose — Pawrrtal does not need a ``paused`` or
``waiting_for_review`` state in v1; if those land, add them here and
update :data:`SUBAGENT_TERMINAL_STATUSES` accordingly.
"""

SUBAGENT_STATUSES: frozenset[str] = frozenset({"running", "succeeded", "failed", "cancelled"})

SUBAGENT_TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class Subagent(Base):
    """One spawned subagent, durable across HTTP requests.

    The lifecycle is owned by ``app.core.subagents.runner`` (PR 3): the
    runner INSERTs a ``running`` row from ``spawn_subagent.execute``,
    then UPDATEs it to a terminal status when the background
    ``asyncio.Task`` finishes.

    Cascade behaviour:

      * ``conversation_id`` ↦ ``conversations.id`` ``ON DELETE CASCADE``.
        Per Tavi 2026-05-18: deleting a conversation removes its
        subagent history.  The app-level
        :func:`app.crud.subagent.cancel_running_subagents_for_conversation`
        hook (PR 2) runs *before* the cascade so the in-process
        registry (PR 3) can also stop live tasks; the DB cascade is
        the safety net for tasks running on a different worker.
      * ``parent_user_id`` ↦ ``user.id`` ``ON DELETE CASCADE``.  When a
        user is deleted every artefact they owned goes with them.
      * ``parent_message_id`` ↦ ``chat_messages.id`` ``ON DELETE SET
        NULL``.  Subagents spawn *during* a chat turn — the assistant
        placeholder may not be finalised when the row is created, and
        the parent message may later be regenerated.  Severing the
        link on parent delete preserves the subagent history without
        introducing a stale FK.
      * ``parent_subagent_id`` ↦ ``subagents.id`` ``ON DELETE CASCADE``.
        Killing a parent subagent kills its descendants atomically;
        any other policy makes the depth cap meaningless on cleanup.
    """

    __tablename__ = "subagents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )

    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_subagent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("subagents.id", ondelete="CASCADE"),
        nullable=True,
    )

    #: ``0`` for a subagent spawned directly by the parent chat agent; ``N``
    #: for a subagent spawned by another subagent at depth ``N-1``.  Hard
    #: capped above by ``settings.subagent_max_depth`` at spawn time —
    #: the column stores the actual depth for audit and tooling.
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    persona_name: Mapped[str] = mapped_column(String(_PERSONA_NAME_COL_LEN), nullable=False)
    handle: Mapped[str] = mapped_column(
        String(_HANDLE_COL_LEN), nullable=False, unique=True, index=True
    )
    label: Mapped[str | None] = mapped_column(String(_LABEL_COL_LEN), nullable=True)

    task: Mapped[str] = mapped_column(Text, nullable=False)

    #: One of :data:`SUBAGENT_STATUSES`.  Kept as a plain ``String``
    #: (not a DB-level ENUM) so SQLite tests and Postgres production
    #: stay schema-symmetric — the Python ``Literal`` is the type-safe
    #: gate.  Indexed because the live-subagent count gate
    #: (``WHERE conversation_id=? AND status='running'``) runs on
    #: every spawn.
    status: Mapped[str] = mapped_column(String(_STATUS_COL_LEN), nullable=False, default="running")

    #: List of tool names the parent granted to this subagent at spawn
    #: time.  Persisted so ``list_subagents`` and audit can show exactly
    #: which capabilities the child had — not derived from persona,
    #: because the parent may have requested a subset.
    tools_granted: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    #: Final assistant text the child produced.  ``None`` while
    #: ``status="running"``; populated on terminal status.  Long-form so
    #: a researcher's multi-paragraph reply isn't truncated.
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Human-readable failure reason when ``status="failed"``.  Excluded
    #: from the parent's view of ``result`` so the parent model
    #: can tell success from failure without parsing the body.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    spawned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # Hot lookup: "what subagents does this conversation have?"
        # for the list_subagents tool and the cascade-cancel hook.
        Index("ix_subagents_conversation_id", "conversation_id"),
        # Hot lookup: "is this conversation already at the fan-out cap?"
        # — counts WHERE conversation_id=? AND status='running'.
        Index(
            "ix_subagents_conversation_status",
            "conversation_id",
            "status",
        ),
    )


__all__: list[str] = [
    "SUBAGENT_STATUSES",
    "SUBAGENT_TERMINAL_STATUSES",
    "Subagent",
    "SubagentStatus",
]


# Module-import-time invariant: the Python literal and the runtime set
# must agree.  Explicit raise (not assert) so ``python -O`` cannot strip
# it — the cost ledger's daily cap relies on this set being correct
# whenever PR 3 inserts a row.
_LITERAL_STATUSES = {"running", "succeeded", "failed", "cancelled"}
if set(SUBAGENT_STATUSES) != _LITERAL_STATUSES:
    raise RuntimeError(
        f"SUBAGENT_STATUSES drifted from SubagentStatus literal: "
        f"literal={_LITERAL_STATUSES} set={set(SUBAGENT_STATUSES)}"
    )
