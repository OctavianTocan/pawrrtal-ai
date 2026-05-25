"""HEARTBEAT.md parser — workspace-scoped scheduled-check definitions.

Each pawrrtal workspace owns a ``HEARTBEAT.md`` file with YAML front
matter listing the periodic checks the agent should run. The file is
seeded by ``app.core.workspace.seed_workspace`` and re-read on demand
by the sync helper in ``app.crud.heartbeat``.

Modelled on openclaw's heartbeat (https://docs.openclaw.ai/gateway/heartbeat),
this module owns the *pure* parsing concerns — schema, validation,
disk read — so the API and CRUD layers can import a typed
``HeartbeatConfig`` without reaching for filesystem internals. Per the
sentrux rule (``entry → api → crud → models → core``), this file MUST
NOT import from ``app.crud.*`` or ``app.api.*``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Front-matter fence mirroring DESIGN.md + openclaw conventions.
FRONT_MATTER_DELIMITER = "---"
# Hard floor on check-name length so APScheduler job ids stay readable.
MAX_CHECK_NAME_LEN = 64


class HeartbeatCheck(BaseModel):
    """One scheduled check inside ``HEARTBEAT.md``.

    ``name`` doubles as a stable identifier the sync helper composes
    into the APScheduler job id (``heartbeat:<workspace_id>:<name>``)
    so re-syncing replaces the existing job in place rather than
    duplicating it.

    ``cron`` is a 5-field cron expression handed straight to
    ``CronTrigger.from_crontab``. Validating here means a malformed
    expression surfaces at parse time, not on the first scheduler fire.

    ``prompt`` is the verbatim text fed to the agent loop when the
    job fires.
    """

    name: str = Field(min_length=1, max_length=MAX_CHECK_NAME_LEN)
    cron: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Reject whitespace; the value lands in an APScheduler job id."""
        if any(ch.isspace() for ch in value):
            raise ValueError("heartbeat check `name` must not contain whitespace")
        return value

    @field_validator("cron")
    @classmethod
    def _validate_cron(cls, value: str) -> str:
        """Reject malformed cron expressions at parse time.

        ``CronTrigger.from_crontab`` raises on bad input. We surface
        the underlying message so the parser error is actionable.
        """
        try:
            CronTrigger.from_crontab(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid cron expression: {exc}") from exc
        return value


class HeartbeatConfig(BaseModel):
    """The full parsed ``HEARTBEAT.md`` document."""

    checks: list[HeartbeatCheck] = Field(default_factory=list)

    def find_check(self, name: str) -> HeartbeatCheck | None:
        """Return the check named ``name``, or ``None`` when absent."""
        for check in self.checks:
            if check.name == name:
                return check
        return None


def parse_heartbeat_md(text: str) -> HeartbeatConfig:
    """Parse the YAML front matter out of a ``HEARTBEAT.md`` string.

    Returns an empty config when no front matter is present so the
    sync helper can degrade gracefully (registers no jobs) without
    raising. Real malformed YAML or schema violations still raise.
    """
    front_matter = _extract_front_matter(text)
    if front_matter is None:
        logger.info("HEARTBEAT_MD_NO_FRONT_MATTER")
        return HeartbeatConfig()
    try:
        raw = yaml.safe_load(front_matter) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"HEARTBEAT.md front matter is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("HEARTBEAT.md front matter must be a YAML mapping")
    return HeartbeatConfig.model_validate(raw)


def load_heartbeat_md(path: Path) -> HeartbeatConfig:
    """Read and parse a ``HEARTBEAT.md`` file from disk.

    Returns an empty config when the file is missing so a workspace
    that hasn't been re-seeded (or that the user deleted the file
    from) doesn't break the sync endpoint.
    """
    if not path.exists():
        logger.info("HEARTBEAT_MD_MISSING path=%s", path)
        return HeartbeatConfig()
    return parse_heartbeat_md(path.read_text(encoding="utf-8"))


def _extract_front_matter(text: str) -> str | None:
    """Return the YAML between two ``---`` fences at the top of ``text``.

    Returns ``None`` when the document does not open with a fence —
    i.e. when the file is pure markdown with no config.
    """
    stripped = text.lstrip()
    if not stripped.startswith(FRONT_MATTER_DELIMITER):
        return None
    remainder = stripped[len(FRONT_MATTER_DELIMITER) :]
    if remainder.startswith("\n"):
        remainder = remainder[1:]
    closing_index = remainder.find(f"\n{FRONT_MATTER_DELIMITER}")
    if closing_index == -1:
        # Unclosed fence — let downstream validation surface the issue.
        return remainder
    return remainder[:closing_index]
