"""Pydantic schemas for the governance + ops platform routers.

Split out of :mod:`app.schemas` to keep that module under the project's
500-line file budget. Imports stay backwards-compatible — every name
exported here is re-exported from :mod:`app.schemas`, so any code still
doing ``from app.schemas import AuditEventRead`` continues to work.

Mirrors the ORM models in :mod:`app.governance_models` (PR 01) so the
new routers (PR 02 audit, PR 04 cost, PR 11 webhooks, PR 12 scheduler)
have stable HTTP contracts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

# Default page size for list endpoints over the new governance tables.
# Matches the convention on the existing conversations endpoint.
DEFAULT_GOVERNANCE_PAGE_SIZE = 100
# Upper bound on a single page to prevent runaway responses.
MAX_GOVERNANCE_PAGE_SIZE = 1000


class AuditEventRead(BaseModel):
    """A single audit log row returned by ``GET /api/v1/audit``."""

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    event_type: str
    success: bool
    risk_level: Literal["low", "medium", "high", "critical"]
    details: dict[str, Any] | None = None
    surface: str | None = None
    request_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CostLedgerRead(BaseModel):
    """A single turn's spend row returned by ``GET /api/v1/cost/ledger``."""

    id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    provider: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    surface: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CostSummaryRead(BaseModel):
    """Aggregate spend view returned by ``GET /api/v1/cost``.

    Drives the small cost gauge in the user settings UI and the 402
    body when the per-window cap is exceeded.
    """

    window_hours: int
    current_usd: float
    limit_usd: float | None = None
    remaining_usd: float | None = None
    # Optional breakdown — only populated when the caller passes
    # `?breakdown=model`. Each entry is `{model_id, cost_usd, turns}`.
    per_model: list[dict[str, Any]] | None = None


class ScheduledJobRead(BaseModel):
    """Schedule + last-fire status returned by ``GET /api/v1/scheduled-jobs``."""

    id: uuid.UUID
    name: str
    cron_expression: str
    prompt: str
    skill_name: str | None = None
    target_chat_ids: list[str] = []
    target_conversation_id: uuid.UUID | None = None
    working_directory: str | None = None
    last_status: str | None = None
    last_fired_at: datetime | None = None
    last_error: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduledJobCreate(BaseModel):
    """Request body for ``POST /api/v1/scheduled-jobs``.

    The scheduler validates ``cron_expression`` against
    ``CronTrigger.from_crontab`` at handler time; an invalid expression
    surfaces as a 422 rather than blowing up at fire time.
    """

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    cron_expression: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    prompt: Annotated[str, StringConstraints(min_length=1)]
    skill_name: str | None = None
    target_chat_ids: list[str] = []
    target_conversation_id: uuid.UUID | None = None
    working_directory: str | None = None


class ScheduledJobUpdate(BaseModel):
    """Partial-update body for ``PATCH /api/v1/scheduled-jobs/{id}``."""

    name: str | None = None
    cron_expression: str | None = None
    prompt: str | None = None
    skill_name: str | None = None
    target_chat_ids: list[str] | None = None
    target_conversation_id: uuid.UUID | None = None
    working_directory: str | None = None
    is_active: bool | None = None


class WebhookEventRead(BaseModel):
    """Inbound webhook delivery row, exposed for diagnostics only."""

    id: uuid.UUID
    provider: str
    event_type: str
    delivery_id: str
    processed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
