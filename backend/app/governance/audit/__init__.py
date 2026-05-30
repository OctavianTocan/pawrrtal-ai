"""Typed audit log with risk levels.

Ported in shape from claude-code-telegram's ``src/security/audit.py``,
adapted to:

* persist every event to the ``audit_events`` table (Postgres / SQLite
  via SQLAlchemy async session) instead of an in-memory list,
* take an ``AsyncSession`` on every helper so the chat router /
  middleware can write inside the existing request transaction,
* automatically stamp ``request_id`` from
  :func:`app.infrastructure.middleware.logging.get_request_id` so each audit row
  correlates with the matching ``REQ_IN``/``REQ_OUT`` log lines and
  any OpenTelemetry span emitted by the same request,
* call into :mod:`app.governance.secret_redaction` so a tool
  input that happens to contain an API key is redacted at the audit
  boundary before the JSON blob is persisted.

Risk-level heuristics (``assess_command_risk`` /
``assess_file_access_risk``) are copied wholesale — they're the same
classifier CCT uses and they map cleanly onto our threat model.

The vocabulary of ``event_type`` values is open (no enum) so new
types can be added without a migration. ``AUDIT_EVENT_TYPES`` below
documents the current canonical set; treat it as descriptive, not
restrictive.

Settings
--------
* ``settings.audit_log_enabled`` — when False, every helper short-
  circuits before touching the DB. The dashboard query still serves
  historical rows.
* ``settings.audit_log_retention_days`` — drives the retention purge
  (called from the scheduler lifespan in PR 12).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.secret_redaction import redact_mapping
from app.infrastructure.config import settings
from app.infrastructure.middleware.logging import get_request_id
from app.models import AuditEvent

logger = logging.getLogger(__name__)

RiskLevel = Literal["low", "medium", "high", "critical"]

# Canonical risk-level vocabulary. Persisted as a String column so new
# values are accepted without migrations — kept here for documentation
# + dashboard query enums.
RISK_LEVELS: tuple[RiskLevel, ...] = ("low", "medium", "high", "critical")

# Canonical event-type vocabulary. Persisted as a String column for
# the same reason as risk levels — extension without migration.
AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "auth_attempt",
        "session",
        "tool_call",
        "file_access",
        "security_violation",
        "rate_limit_exceeded",
        "cost_limit_exceeded",
        "webhook_delivery",
        "scheduled_job_fired",
    }
)


# Truncate detail blobs at this length when stringified for logs.
# Storage column accepts arbitrary JSON so we don't truncate the
# DB row; this only affects the operator-facing log line.
_LOG_DETAILS_PREVIEW_LEN = 200

# Risk-classifier vocabularies. Lifted straight from CCT's
# ``_assess_command_risk`` and ``_assess_file_access_risk`` so the
# upstream-side and our-side classifications stay aligned.
_HIGH_RISK_COMMANDS: frozenset[str] = frozenset(
    {
        "rm",
        "del",
        "delete",
        "format",
        "fdisk",
        "dd",
        "chmod",
        "chown",
        "sudo",
        "su",
        "passwd",
        "curl",
        "wget",
        "ssh",
        "scp",
        "rsync",
    }
)

_MEDIUM_RISK_COMMANDS: frozenset[str] = frozenset(
    {
        "git",
        "npm",
        "pip",
        "docker",
        "kubectl",
        "make",
        "cmake",
        "gcc",
        "python",
        "node",
    }
)

_SENSITIVE_PATH_FRAGMENTS: tuple[str, ...] = (
    "/etc/",
    "/var/",
    "/usr/",
    "/sys/",
    "/proc/",
    "/.env",
    "/.ssh/",
    "/.aws/",
    "/secrets/",
    "config",
    "password",
    "key",
    "token",
)

_RISKY_FILE_ACTIONS: frozenset[str] = frozenset({"delete", "write"})


def assess_command_risk(command: str, args: Iterable[str] | None = None) -> RiskLevel:
    """Classify the risk of executing ``command`` with ``args``.

    Mirrors CCT's heuristic: tier the base command against the
    high/medium command sets; anything else is ``low``. ``args``
    is accepted for API symmetry with CCT, currently ignored.
    """
    _ = args  # parity with CCT signature; not used in the heuristic
    base = command.lower()
    if any(risky in base for risky in _HIGH_RISK_COMMANDS):
        return "high"
    if any(risky in base for risky in _MEDIUM_RISK_COMMANDS):
        return "medium"
    return "low"


def assess_file_access_risk(file_path: str, action: str) -> RiskLevel:
    """Classify the risk of ``action`` against ``file_path``.

    Sensitive paths (``/etc``, ``/.ssh``, anything containing ``key``
    or ``token`` …) combined with a risky action (``write`` / ``delete``)
    are ``high``; either dimension alone is ``medium``; otherwise ``low``.
    """
    path = file_path.lower()
    is_sensitive = any(fragment in path for fragment in _SENSITIVE_PATH_FRAGMENTS)
    is_risky_action = action in _RISKY_FILE_ACTIONS
    if is_sensitive and is_risky_action:
        return "high"
    if is_sensitive or is_risky_action:
        return "medium"
    return "low"


@dataclass(frozen=True)
class AuditRecord:
    """In-memory snapshot of an audit event.

    Lightweight value object the ``AuditLogger`` returns from each
    ``log_*`` helper so call sites can attach the audit row's ID to
    an OTel span / structured log line without re-querying the DB.
    """

    id: uuid.UUID
    user_id: uuid.UUID | None
    event_type: str
    success: bool
    risk_level: RiskLevel
    details: dict[str, Any] | None
    surface: str | None
    request_id: str | None
    created_at: datetime


@dataclass
class AuditLogger:
    """Async audit logger with structured ``log_*`` helpers.

    Every helper:

    1. Checks ``settings.audit_log_enabled`` and short-circuits early
       when disabled. The return value is ``None`` in that case so
       callers can ignore the result without a runtime exception.
    2. Redacts ``details`` via :func:`redact_mapping` so secrets
       pasted into tool inputs never reach the audit table.
    3. Stamps ``request_id`` from
       :func:`app.infrastructure.middleware.logging.get_request_id` so audit rows
       correlate with HTTP log lines.
    4. ``session.add()``s the ORM row; the caller commits as part of
       its request transaction. This means a failed request rolls
       audit rows back too, which is the right behaviour — partial
       work shouldn't leave half-truth audit trails.

    For audit emission outside a request (cron, webhook delivery
    handler), open a new session and commit inside the helper —
    the ``commit`` argument makes that one-line.
    """

    session: AsyncSession
    surface: str | None = None
    _high_risk_threshold: tuple[RiskLevel, ...] = field(default=("high", "critical"), repr=False)

    async def log(
        self,
        *,
        event_type: str,
        user_id: uuid.UUID | None,
        success: bool = True,
        risk_level: RiskLevel = "low",
        details: Mapping[str, Any] | None = None,
        commit: bool = False,
    ) -> AuditRecord | None:
        """Record a single typed audit event.

        Args:
            event_type: One of :data:`AUDIT_EVENT_TYPES` (open set).
            user_id: User the event is attributed to, or ``None`` for
                system / unauthenticated events (e.g. an unknown
                webhook delivery).
            success: True for successful actions, False for failures.
                ``security_violation`` events should set this False.
            risk_level: Authoring-side override. The classifier
                helpers (:func:`assess_command_risk`,
                :func:`assess_file_access_risk`) are typically called
                first and their result fed in here.
            details: Structured payload. Secret-redacted before
                persistence.
            commit: When True the session is committed at the end.
                Useful for one-shot writes from background tasks.
        """
        if not settings.audit_log_enabled:
            return None

        safe_details: dict[str, Any] | None
        if details is None:
            safe_details = None
        else:
            redacted = redact_mapping(dict(details))
            safe_details = redacted if isinstance(redacted, dict) else None

        request_id = get_request_id()
        # Treat the contextvar default ("-") as absent so the
        # audit row's request_id stays NULL for cron / webhook
        # writes that don't run inside an HTTP request.
        normalised_request_id = request_id if request_id and request_id != "-" else None

        now = datetime.now(UTC)
        row = AuditEvent(
            id=uuid.uuid4(),
            user_id=user_id,
            event_type=event_type,
            success=success,
            risk_level=risk_level,
            details=safe_details,
            surface=self.surface,
            request_id=normalised_request_id,
            created_at=now,
        )
        self.session.add(row)
        if commit:
            await self.session.commit()

        if risk_level in self._high_risk_threshold:
            preview = _stringify_details(safe_details)
            logger.warning(
                "AUDIT_HIGH_RISK event_type=%s user_id=%s risk=%s details=%s",
                event_type,
                user_id,
                risk_level,
                preview,
            )
        else:
            logger.info(
                "AUDIT event_type=%s user_id=%s risk=%s success=%s",
                event_type,
                user_id,
                risk_level,
                success,
            )

        return AuditRecord(
            id=row.id,
            user_id=row.user_id,
            event_type=row.event_type,
            success=row.success,
            risk_level=row.risk_level,  # type: ignore[arg-type]
            details=row.details,
            surface=row.surface,
            request_id=row.request_id,
            created_at=row.created_at,
        )

    # ── Convenience helpers — same vocabulary as CCT ─────────────────────

    async def log_auth_attempt(
        self,
        *,
        user_id: uuid.UUID | None,
        success: bool,
        method: str,
        reason: str | None = None,
        commit: bool = False,
    ) -> AuditRecord | None:
        """Authentication attempt (login, token, OAuth callback)."""
        return await self.log(
            event_type="auth_attempt",
            user_id=user_id,
            success=success,
            risk_level="medium" if not success else "low",
            details={"method": method, "reason": reason},
            commit=commit,
        )

    async def log_tool_call(
        self,
        *,
        user_id: uuid.UUID,
        tool_name: str,
        tool_input: Mapping[str, Any] | None,
        success: bool,
        risk_level: RiskLevel = "low",
        duration_ms: float | None = None,
        commit: bool = False,
    ) -> AuditRecord | None:
        """Single tool invocation from the agent loop.

        ``tool_input`` is redacted before persistence (the audit row
        keeps the same shape minus any embedded secrets). For
        ``bash``-shaped tools the caller should compute ``risk_level``
        via :func:`assess_command_risk` first.
        """
        details: dict[str, Any] = {"tool_name": tool_name}
        if tool_input is not None:
            details["input"] = dict(tool_input)
        if duration_ms is not None:
            details["duration_ms"] = round(duration_ms, 2)
        return await self.log(
            event_type="tool_call",
            user_id=user_id,
            success=success,
            risk_level=risk_level,
            details=details,
            commit=commit,
        )

    async def log_file_access(
        self,
        *,
        user_id: uuid.UUID,
        file_path: str,
        action: Literal["read", "write", "delete", "create"],
        success: bool,
        commit: bool = False,
    ) -> AuditRecord | None:
        """File-system access from a tool execution."""
        return await self.log(
            event_type="file_access",
            user_id=user_id,
            success=success,
            risk_level=assess_file_access_risk(file_path, action),
            details={"file_path": file_path, "action": action},
            commit=commit,
        )

    async def log_security_violation(
        self,
        *,
        user_id: uuid.UUID | None,
        violation_type: str,
        details: str,
        severity: Literal["low", "medium", "high"] = "medium",
        attempted_action: str | None = None,
        commit: bool = False,
    ) -> AuditRecord | None:
        """Permission-denied tool call, path traversal, etc.

        Severity is mapped onto risk_level via CCT's table so a
        ``security_violation`` is always one notch higher than the
        equivalent successful event.
        """
        severity_to_risk: dict[str, RiskLevel] = {
            "low": "medium",
            "medium": "high",
            "high": "critical",
        }
        return await self.log(
            event_type="security_violation",
            user_id=user_id,
            success=False,
            risk_level=severity_to_risk[severity],
            details={
                "violation_type": violation_type,
                "details": details,
                "severity": severity,
                "attempted_action": attempted_action,
            },
            commit=commit,
        )

    async def log_rate_limit_exceeded(
        self,
        *,
        user_id: uuid.UUID,
        limit_type: Literal["request", "cost"],
        current_usage: float,
        limit_value: float,
        commit: bool = False,
    ) -> AuditRecord | None:
        """A rate-limit / cost-budget gate fired."""
        utilisation = current_usage / limit_value if limit_value > 0 else 0
        return await self.log(
            event_type="rate_limit_exceeded" if limit_type == "request" else "cost_limit_exceeded",
            user_id=user_id,
            success=False,
            risk_level="low",
            details={
                "limit_type": limit_type,
                "current_usage": current_usage,
                "limit_value": limit_value,
                "utilisation": round(utilisation, 4),
            },
            commit=commit,
        )

    async def log_webhook_delivery(
        self,
        *,
        provider: str,
        event_type_name: str,
        delivery_id: str,
        success: bool,
        user_id: uuid.UUID | None = None,
        commit: bool = False,
    ) -> AuditRecord | None:
        """One inbound webhook delivery decision (accepted / rejected)."""
        return await self.log(
            event_type="webhook_delivery",
            user_id=user_id,
            success=success,
            risk_level="medium" if not success else "low",
            details={
                "provider": provider,
                "event_type": event_type_name,
                "delivery_id": delivery_id,
            },
            commit=commit,
        )

    async def log_scheduled_job_fired(
        self,
        *,
        job_id: uuid.UUID,
        job_name: str,
        user_id: uuid.UUID | None,
        success: bool,
        commit: bool = False,
    ) -> AuditRecord | None:
        """A scheduler-triggered job ran (or failed to run)."""
        return await self.log(
            event_type="scheduled_job_fired",
            user_id=user_id,
            success=success,
            risk_level="low",
            details={"job_id": str(job_id), "job_name": job_name},
            commit=commit,
        )


def _stringify_details(details: dict[str, Any] | None) -> str:
    """Render a details blob to a short log-line preview."""
    if not details:
        return "{}"
    text = ", ".join(f"{k}={v!r}" for k, v in details.items())
    if len(text) > _LOG_DETAILS_PREVIEW_LEN:
        return text[: _LOG_DETAILS_PREVIEW_LEN - 1] + "…"
    return text
