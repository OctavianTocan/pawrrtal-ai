"""ORM models for the governance + ops platform tables.

Split out of :mod:`app.models` to keep that module under the project's
500-line file budget. Imports stay backwards-compatible — every name
TODO: I do not want this backwards compatibility crap.
exported here is re-exported from :mod:`app.models`, so any code still
doing ``from app.models import AuditEvent`` continues to work.

Four tables back the cross-cutting policy + automation surface:

* ``audit_events``  — append-only security/operational log with
  risk levels (``auth_attempt``, ``tool_call``, ``security_violation``,
  ``cost_limit_exceeded``, …).
* ``cost_ledger``   — one row per LLM turn, source of truth for spend
  rollups (``GET /api/v1/cost``, budget gate).
* ``scheduled_jobs`` — durable cron job definitions; APScheduler
  hydrates these on boot and re-registers triggers.
* ``webhook_events`` — inbound webhook deliveries; the ``delivery_id``
  unique index powers atomic ``INSERT … ON CONFLICT DO NOTHING``
  dedupe.

Each follows the existing conventions (Uuid PK, FK to user with
CASCADE, JSON for flexible payloads, ``created_at`` on every row).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from app.infrastructure.models.base import Base

# --- Column-length sizing constants ----------------------------------

# Maximum length of an audit event type string. 64 covers every documented
# type with room for future extension without a column-resize migration.
_AUDIT_EVENT_TYPE_LEN = 64
# Length cap for risk-level strings (`low`/`medium`/`high`/`critical`).
_AUDIT_RISK_LEVEL_LEN = 16
# Provider identifier length: comfortably fits `claude-agent-sdk` and
# common provider slugs without forcing future migrations.
_COST_PROVIDER_LEN = 64
# Model-id length matches the existing column on `conversations`.
_MODEL_ID_LEN = 100
# Scheduled-job name length: human-readable label, not a slug.
_SCHEDULED_JOB_NAME_LEN = 128
# Cron expression length (5-field cron tops out around 100 chars in
# practice — APScheduler also accepts seconds-precision 6-field).
_CRON_EXPRESSION_LEN = 128
# Status length for scheduled_jobs (`pending`/`running`/`completed`/`failed`).
_SCHEDULED_JOB_STATUS_LEN = 16
# Skill identifier length on scheduled jobs (optional, e.g. `triage`).
_SKILL_NAME_LEN = 64
# Webhook provider slug length (`github`, `linear`, `stripe`, …).
_WEBHOOK_PROVIDER_LEN = 32
# Webhook event-type length (e.g. `push`, `pull_request.opened`).
_WEBHOOK_EVENT_TYPE_LEN = 64
# Delivery-id length sized for GitHub's UUID-ish delivery headers.
_WEBHOOK_DELIVERY_ID_LEN = 128


class AuditEvent(Base):
    """Append-only audit log for security and operational events.

    Ported in shape from claude-code-telegram's ``src/security/audit.py``,
    backed by SQLAlchemy + Postgres instead of in-memory. Every row is
    immutable; the application never updates or deletes rows except via
    the retention purge job (which deletes whole rows older than the
    configured TTL — never edits them).

    The ``event_type`` set is open (no enum) so new types can be added
    without a migration; the canonical vocabulary is documented in
    ``backend/app/core/governance/audit.py`` (PR 02).

    ``risk_level`` is one of ``low|medium|high|critical`` and is computed
    by the audit logger from the event_type + details payload. It is
    persisted so the dashboard query can aggregate without re-deriving.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # NULL when the event isn't user-attributable (e.g. webhook delivery
    # with an unknown signature). Most events have a user.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(_AUDIT_EVENT_TYPE_LEN), index=True)
    # True for `auth_attempt: success=True` etc. Always False for
    # `security_violation` (CCT convention).
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    risk_level: Mapped[str] = mapped_column(
        String(_AUDIT_RISK_LEVEL_LEN), nullable=False, default="low"
    )
    # Arbitrary structured payload. Tool inputs persisted here are
    # always pre-redacted by ``governance.secret_redaction`` (PR 02).
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Surface that originated the event (`web`, `telegram`, `webhook`, …).
    surface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Request ID from ``request_logging.get_request_id()`` so audit rows
    # correlate with log lines and OTel spans.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class CostLedger(Base):
    """One row per LLM turn, source of truth for spend rollups.

    The chat router writes a row per turn after the provider emits its
    ``usage`` event (PR 04). Aggregations for the cost gate
    (``GET /api/v1/cost`` and the ``CostBudgetMiddleware``) run as
    indexed SQL over this table.

    ``cost_usd`` is the authoritative value — for Claude it comes from
    ``ResultMessage.total_cost_usd``; for Gemini it's computed by
    multiplying token counts against the per-mtok rates registered on
    the catalog (``ModelEntry.cost_per_mtok_*_usd``).
    """

    __tablename__ = "cost_ledger"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(_COST_PROVIDER_LEN))
    model_id: Mapped[str] = mapped_column(String(_MODEL_ID_LEN))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Stored as Float for simplicity. The values are dollar-cents-scale
    # so float rounding is well below a cent.
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    # Surface lets us partition spend by web vs telegram vs webhook in
    # reporting without a JOIN.
    surface: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class ScheduledJob(Base):
    """Durable cron job definition; APScheduler re-registers on boot.

    The scheduler (PR 12) reads every active row on startup and
    re-installs the corresponding cron trigger. New jobs go through
    ``POST /api/v1/scheduled-jobs`` which writes here AND adds to the
    live scheduler in one transaction.

    Soft-delete via ``is_active`` so historical jobs can be inspected
    for audit / debugging (the scheduler skips ``is_active=False``).
    """

    __tablename__ = "scheduled_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(_SCHEDULED_JOB_NAME_LEN))
    cron_expression: Mapped[str | None] = mapped_column(String(_CRON_EXPRESSION_LEN), nullable=True)
    # Specific time to fire the job, for one-shot reminders. Mutually exclusive with cron_expression.
    fire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Prompt the agent runs when the job fires.
    prompt: Mapped[str] = mapped_column(Text)
    # Optional skill to invoke (`/triage`, etc.) — prepended to the prompt.
    skill_name: Mapped[str | None] = mapped_column(String(_SKILL_NAME_LEN), nullable=True)
    # Telegram chat IDs the result is delivered to, persisted as a JSON
    # array of strings (chat IDs can exceed 32-bit signed range).
    target_chat_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Optional conversation to persist the agent response into when the
    # job fires. Cleared (NULL) when the conversation is deleted so the
    # job keeps running and only the web-side mirror is lost.
    target_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Optional working-directory hint — defaults to the user's workspace.
    working_directory: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    # Lifecycle: `pending` → `running` → `completed`|`failed`. NULL until
    # the first fire.
    last_status: Mapped[str | None] = mapped_column(
        String(_SCHEDULED_JOB_STATUS_LEN), nullable=True
    )
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class WebhookEventRecord(Base):
    """Inbound webhook delivery, persisted for atomic dedupe + audit.

    The receiver (PR 11) inserts a row with ``INSERT … ON CONFLICT
    DO NOTHING`` on ``delivery_id``. If 1 row was inserted, the event
    is new and gets published to the bus; if 0, it's a duplicate and
    the receiver returns ``{"status": "duplicate"}`` without re-firing
    the agent.

    ``user_id`` is NULL when the webhook isn't user-attributable; for
    GitHub events we can usually map the repo owner to a user via a
    future workspace-link table (PR not in this stack).
    """

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(_WEBHOOK_PROVIDER_LEN), index=True)
    event_type: Mapped[str] = mapped_column(String(_WEBHOOK_EVENT_TYPE_LEN))
    # Provider-supplied delivery identifier (e.g. GitHub's
    # `X-GitHub-Delivery` header). Indexed UNIQUE for the dedupe insert.
    delivery_id: Mapped[str] = mapped_column(
        String(_WEBHOOK_DELIVERY_ID_LEN), unique=True, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Was the resulting `WebhookEvent` ever delivered to an agent? NULL
    # until the AgentHandler picks it up; populated when the response
    # is delivered.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
