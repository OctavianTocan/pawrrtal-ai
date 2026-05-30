"""canonicalise legacy conversation.model_id values

Pre-PR-#178 rows carry bare model names (``claude-haiku-4-5``,
``gemini-3.1-flash-lite-preview``) or empty strings. The read-side
Pydantic validator (``CanonicalModelIdForRead``) rejects anything that
doesn't match ``[host:]vendor/model``, so ``GET /api/v1/conversations``
500s on the first legacy row it encounters.

This migration rewrites every legacy value to its canonical
``host:vendor/model`` form using the same vendor → host mapping the
catalog uses (``catalog.MODEL_CATALOG``). Empty strings become
``NULL`` so the validator's ``None`` early-return covers them.

The mapping is hand-rolled (not imported from
``app.providers.catalog``) on purpose: Alembic migrations must
stay runnable even if the catalog module changes shape later. If the
catalog renames a model the migration still reflects the *historical*
identifiers that ever existed in the database.

Revision ID: 012_canonicalise_conversation_model_ids
Revises: 011_add_channel_columns_and_attachment
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_canonicalise_conversation_model_ids"
down_revision: Union[str, Sequence[str], None] = "011_add_channel_columns_and_attachment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Legacy bare model name → canonical ``host:vendor/model``.
# Covers every value the application ever wrote before PR #178 landed
# the canonical-ID contract. Add a row here if a future legacy survey
# turns up a value not in this map.
LEGACY_MODEL_ID_MAP: dict[str, str] = {
    "claude-opus-4-7": "agent-sdk:anthropic/claude-opus-4-7",
    "claude-sonnet-4-6": "agent-sdk:anthropic/claude-sonnet-4-6",
    "claude-haiku-4-5": "agent-sdk:anthropic/claude-haiku-4-5",
    "gemini-3-flash-preview": "google-ai:google/gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview": "google-ai:google/gemini-3.1-flash-lite-preview",
}


def upgrade() -> None:
    """Rewrite legacy model_id values to canonical form; blank → NULL."""
    bind = op.get_bind()
    # Backend-neutral parameterised UPDATEs; no DDL involved.
    for legacy, canonical in LEGACY_MODEL_ID_MAP.items():
        bind.execute(
            sa.text("UPDATE conversations SET model_id = :canonical WHERE model_id = :legacy"),
            {"canonical": canonical, "legacy": legacy},
        )
    # Empty strings predate the bare-name format; map them to NULL so
    # the read validator's ``raw is None`` early-return covers them.
    bind.execute(sa.text("UPDATE conversations SET model_id = NULL WHERE model_id = ''"))


def downgrade() -> None:
    """Restore the bare model name for each canonical value we rewrote.

    The empty-string → NULL rewrite isn't reversed: there's no way to
    distinguish rows that started as ``''`` from rows that started as
    NULL, and ``NULL`` is the correct shape for "no model selected"
    going forward.
    """
    bind = op.get_bind()
    for legacy, canonical in LEGACY_MODEL_ID_MAP.items():
        bind.execute(
            sa.text("UPDATE conversations SET model_id = :legacy WHERE model_id = :canonical"),
            {"legacy": legacy, "canonical": canonical},
        )
