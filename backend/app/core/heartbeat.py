"""Heartbeat configuration model and `HEARTBEAT.md` parser.

The heartbeat is a periodic background agent turn, modelled on openclaw's
`Heartbeat` feature.  This module owns the *pure* concerns — config schema
and front-matter parsing — so the API and scheduler layers can import a
fully-typed `HeartbeatConfig` without reaching for filesystem internals.

The sentrux layering rule (`entry → api → crud → models → core`) means
this file MUST NOT import from `app.crud.*` or `app.api.*`.  Anything that
touches the database or the chat pipeline lives one layer up in
`app.api.heartbeat`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Front-matter delimiter mirroring the openclaw + DESIGN.md convention.
FRONT_MATTER_DELIMITER = "---"
# Hard floor on per-check cadence.  APScheduler accepts smaller intervals
# but a sub-minute heartbeat is almost certainly a misconfiguration — the
# LLM-backed runs are not cheap and we don't want a typo to burn through
# tokens.  Raise the floor here rather than per-call so a single check
# can't bypass the rule.
MIN_INTERVAL_SECONDS = 60


class HeartbeatCheck(BaseModel):
    """One scheduled check inside `HEARTBEAT.md`.

    `name` is the stable identifier APScheduler uses for the job id; the
    runner also tags persisted messages with it so we can later filter the
    chat UI to "show me the last seven `pulse` checks".

    `prompt` is the verbatim text the future LLM-backed runner will hand
    to the agent loop.  For the tracer slice the prompt is echoed into the
    persisted assistant message so an operator can see exactly what would
    have been sent.
    """

    name: str = Field(min_length=1, max_length=64)
    interval_seconds: int = Field(ge=MIN_INTERVAL_SECONDS)
    prompt: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Reject names with whitespace — they double as APScheduler job ids."""
        if any(ch.isspace() for ch in value):
            raise ValueError("heartbeat check `name` must not contain whitespace")
        return value


class HeartbeatConfig(BaseModel):
    """The full parsed `HEARTBEAT.md` document."""

    checks: list[HeartbeatCheck] = Field(default_factory=list)

    def find_check(self, name: str) -> HeartbeatCheck | None:
        """Return the check with `name`, or None when no such check is defined."""
        for check in self.checks:
            if check.name == name:
                return check
        return None


def parse_heartbeat_md(text: str) -> HeartbeatConfig:
    """Parse the YAML front matter out of a `HEARTBEAT.md` string.

    The body after the front matter is intentionally ignored here — it's
    free-form context for humans (and the future LLM-backed runner reads
    it directly off disk).  Returning an empty config when the document
    has no front matter lets callers degrade gracefully: the scheduler
    simply registers no jobs.

    Raises:
        ValueError: when the front matter is present but malformed YAML
            or fails `HeartbeatConfig` validation.  The scheduler treats
            this as fatal at boot so misconfig surfaces immediately
            rather than after the first interval elapses.
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
    """Read and parse a `HEARTBEAT.md` file from disk.

    Returns an empty config when the file is missing so the scheduler can
    boot in environments that haven't opted into heartbeat (the
    `HEARTBEAT_ENABLED` flag in settings is the primary gate, but defence
    in depth keeps the lifespan from crashing if the path is misconfigured
    on a particular deployment).
    """
    if not path.exists():
        logger.info("HEARTBEAT_MD_MISSING path=%s", path)
        return HeartbeatConfig()
    return parse_heartbeat_md(path.read_text(encoding="utf-8"))


def _extract_front_matter(text: str) -> str | None:
    """Return the YAML between two `---` fences at the top of `text`.

    Returns None when the document does not open with a fence — i.e.
    when the file is pure markdown with no config.
    """
    stripped = text.lstrip()
    if not stripped.startswith(FRONT_MATTER_DELIMITER):
        return None
    # Skip the opening fence (plus its newline).
    remainder = stripped[len(FRONT_MATTER_DELIMITER) :]
    if remainder.startswith("\n"):
        remainder = remainder[1:]
    closing_index = remainder.find(f"\n{FRONT_MATTER_DELIMITER}")
    if closing_index == -1:
        # Unclosed fence — treat the whole rest as YAML.  Validation
        # downstream will catch genuinely broken documents.
        return remainder
    return remainder[:closing_index]
