"""Tests for ``app.core.governance.audit``.

Covers:

* every ``log_*`` helper writes a row with the right ``event_type``
  + ``risk_level`` + ``success`` shape,
* ``settings.audit_log_enabled = False`` short-circuits all helpers
  without raising,
* the risk-level classifier picks the right tier for known commands
  and file paths,
* ``redact_mapping`` applies to ``details`` before persistence
  (a token in a tool input never lands in the audit row).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.governance.audit import (
    AuditLogger,
    assess_command_risk,
    assess_file_access_risk,
)
from app.infrastructure.database.legacy import User
from app.models import AuditEvent

pytestmark = pytest.mark.anyio


async def _all_events(session: AsyncSession) -> list[AuditEvent]:
    rows = await session.execute(select(AuditEvent))
    return list(rows.scalars().all())


class TestAuditLoggerHappyPaths:
    """Every helper persists a row with the expected shape."""

    async def test_log_auth_attempt_success(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        logger = AuditLogger(session=db_session, surface="web")
        record = await logger.log_auth_attempt(
            user_id=test_user.id,
            success=True,
            method="password",
        )
        await db_session.commit()

        assert record is not None
        assert record.event_type == "auth_attempt"
        assert record.risk_level == "low"
        rows = await _all_events(db_session)
        assert len(rows) == 1
        assert rows[0].surface == "web"
        assert rows[0].success is True

    async def test_log_auth_attempt_failure_is_medium_risk(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        logger = AuditLogger(session=db_session)
        record = await logger.log_auth_attempt(
            user_id=test_user.id,
            success=False,
            method="password",
            reason="bad-password",
        )
        await db_session.commit()
        assert record is not None
        assert record.risk_level == "medium"
        assert record.success is False

    async def test_log_tool_call_redacts_input(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        logger = AuditLogger(session=db_session)
        record = await logger.log_tool_call(
            user_id=test_user.id,
            tool_name="exa_search",
            tool_input={"query": "ok", "api_key": "TOKEN=verysecret1234567890"},
            success=True,
        )
        await db_session.commit()
        assert record is not None
        # input persisted but the secret value is masked
        rows = await _all_events(db_session)
        assert len(rows) == 1
        assert rows[0].details is not None
        persisted_input = rows[0].details["input"]
        assert "***" in persisted_input["api_key"]
        assert persisted_input["query"] == "ok"

    async def test_log_file_access_high_risk(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        logger = AuditLogger(session=db_session)
        record = await logger.log_file_access(
            user_id=test_user.id,
            file_path="/etc/passwd",
            action="write",
            success=False,
        )
        await db_session.commit()
        assert record is not None
        # write + sensitive path → high
        assert record.risk_level == "high"

    async def test_log_security_violation_promotes_severity(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        logger = AuditLogger(session=db_session)
        record = await logger.log_security_violation(
            user_id=test_user.id,
            violation_type="path_traversal",
            details="attempted ../../etc/passwd",
            severity="medium",
        )
        await db_session.commit()
        assert record is not None
        # medium severity violation maps to "high" risk per the table
        assert record.risk_level == "high"
        assert record.success is False

    async def test_log_rate_limit_exceeded(self, db_session: AsyncSession, test_user: User) -> None:
        logger = AuditLogger(session=db_session)
        record = await logger.log_rate_limit_exceeded(
            user_id=test_user.id,
            limit_type="request",
            current_usage=11,
            limit_value=10,
        )
        await db_session.commit()
        assert record is not None
        assert record.event_type == "rate_limit_exceeded"
        assert record.success is False

    async def test_log_cost_limit_exceeded(self, db_session: AsyncSession, test_user: User) -> None:
        logger = AuditLogger(session=db_session)
        record = await logger.log_rate_limit_exceeded(
            user_id=test_user.id,
            limit_type="cost",
            current_usage=10.5,
            limit_value=10.0,
        )
        await db_session.commit()
        assert record is not None
        assert record.event_type == "cost_limit_exceeded"

    async def test_log_webhook_delivery_failure_is_medium_risk(
        self, db_session: AsyncSession
    ) -> None:
        logger = AuditLogger(session=db_session)
        record = await logger.log_webhook_delivery(
            provider="github",
            event_type_name="push",
            delivery_id="abc-123",
            success=False,
        )
        await db_session.commit()
        assert record is not None
        assert record.risk_level == "medium"
        assert record.user_id is None

    async def test_log_scheduled_job_fired(self, db_session: AsyncSession, test_user: User) -> None:
        logger = AuditLogger(session=db_session)
        job_id = uuid.uuid4()
        record = await logger.log_scheduled_job_fired(
            job_id=job_id,
            job_name="daily-summary",
            user_id=test_user.id,
            success=True,
        )
        await db_session.commit()
        assert record is not None
        assert record.event_type == "scheduled_job_fired"
        assert record.details is not None
        assert record.details["job_name"] == "daily-summary"


class TestAuditDisabled:
    """When the global toggle is off, helpers no-op cleanly."""

    async def test_disabled_returns_none_and_writes_nothing(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "audit_log_enabled", False)
        logger = AuditLogger(session=db_session)
        record = await logger.log_auth_attempt(
            user_id=test_user.id, success=True, method="password"
        )
        assert record is None
        rows = await _all_events(db_session)
        assert rows == []


class TestRiskClassifiers:
    """The heuristics catch the tiers CCT documents."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("rm", "high"),
            ("sudo", "high"),
            ("chmod", "high"),
            ("git", "medium"),
            ("npm", "medium"),
            ("ls", "low"),
            ("echo", "low"),
        ],
    )
    def test_command_risk(self, command: str, expected: str) -> None:
        assert assess_command_risk(command) == expected

    @pytest.mark.parametrize(
        ("path", "action", "expected"),
        [
            ("/etc/passwd", "write", "high"),
            ("/etc/passwd", "read", "medium"),
            ("/home/user/code.py", "write", "medium"),
            ("/home/user/code.py", "read", "low"),
            ("/.ssh/id_rsa", "delete", "high"),
        ],
    )
    def test_file_risk(self, path: str, action: str, expected: str) -> None:
        assert assess_file_access_risk(path, action) == expected
