"""Verify suite primitives — ``ScenarioResult`` / ``Check``.

Every scenario emits a list of named, snake_case checks plus a free-form
``artifacts`` bag so failure modes are greppable and reproducible. The
greppable check name is the canonical contract: tooling (CI, dashboards,
agents debugging a failure) keys off ``checks[].name``, never the human
``detail`` text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Check:
    """One named pass/fail assertion emitted by a scenario step.

    ``name`` is the snake_case identifier (e.g. ``codex_thread_id_persisted``)
    that agents grep for; ``detail`` is a human-readable explanation that
    only appears in the human renderer when the check failed.
    """

    name: str
    passed: bool
    detail: str = ""


@dataclass
class ScenarioResult:
    """Aggregate result of one verification scenario.

    Scenarios append checks via :meth:`add`; the overall ``passed`` flag
    flips to ``False`` the moment any check fails. ``artifacts`` is the
    free-form bag for raw payloads (events, response bodies, durations) so
    a ``--json`` dump is sufficient to diagnose any failure without rerunning.
    """

    name: str
    passed: bool = True
    checks: list[Check] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, passed: bool, detail: str = "") -> ScenarioResult:
        """Append one check; flip ``self.passed`` to ``False`` on any failure."""
        self.checks.append(Check(name=name, passed=passed, detail=detail))
        if not passed:
            self.passed = False
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the wire shape consumed by ``--json`` mode."""
        return {
            "scenario": self.name,
            "passed": self.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks
            ],
            "artifacts": self.artifacts,
        }
