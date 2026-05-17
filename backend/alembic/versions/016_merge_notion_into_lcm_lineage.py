"""Merge notion_operation_logs lineage into the LCM head.

PR #261 added ``013_notion_operation_logs`` as a sibling of
``013_governance_and_jobs`` (both branched off
``012_canonicalise_conversation_model_ids``). The mainline chain ran
on to ``014_drop_active_conversation_id`` → ``015_add_lcm_tables``,
while ``013_notion_operation_logs`` was never reparented onto it, so
``alembic upgrade head`` now sees two heads and fails on Railway boot
with:

    "Multiple head revisions are present for given argument 'head';
     please specify a specific target revision."

This is an empty merge migration that joins both heads at one point so
``alembic upgrade head`` is well-defined again. It applies cleanly on
top of either head — ``alembic upgrade head`` from a database at
``015_add_lcm_tables`` will apply ``013_notion_operation_logs`` first
(via the ``012`` shared parent) and then this merge, producing the
``016_merge_notion_into_lcm_lineage`` head.

Revision ID: 016_merge_notion_into_lcm_lineage
Revises: 013_notion_operation_logs, 015_add_lcm_tables
Create Date: 2026-05-17 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "016_merge_notion_into_lcm_lineage"
down_revision: str | Sequence[str] | None = (
    "013_notion_operation_logs",
    "015_add_lcm_tables",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge-only migration — no schema changes."""


def downgrade() -> None:
    """Merge-only migration — no schema changes."""
