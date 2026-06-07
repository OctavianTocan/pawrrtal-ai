"""Cross-cutting governance modules.

Audit log, secret redaction, cost tracking, and workspace-context
loading. This package grows over the CCT-yoink stack (PRs 02-12):

* :mod:`audit`            — typed audit events with risk levels.
* :mod:`secret_redaction` — regex pass over log lines and tool inputs.
* :mod:`cost_tracker`     — per-turn cost ledger + budget gate (PR 04).
* :mod:`workspace_context` — CLAUDE.md/skills/settings.json reader (PR 06).
* :mod:`middleware`       — Starlette middleware that composes the above.

Each submodule is independent; no circular imports between them. The
chat router / agent loop call into individual modules; nothing reaches
across through ``__init__``.
"""

from app.governance.audit import (
    AUDIT_EVENT_TYPES,
    RISK_LEVELS,
    AuditLogger,
    AuditRecord,
    assess_command_risk,
    assess_file_access_risk,
)
from app.governance.secret_redaction import (
    SECRET_PATTERNS,
    redact_mapping,
    redact_secrets,
)

__all__ = [
    "AUDIT_EVENT_TYPES",
    "RISK_LEVELS",
    "SECRET_PATTERNS",
    "AuditLogger",
    "AuditRecord",
    "assess_command_risk",
    "assess_file_access_risk",
    "redact_mapping",
    "redact_secrets",
]
