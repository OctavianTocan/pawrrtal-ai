"""Pawrrtal exception hierarchy.

Two roots under :class:`PawrrtalError`:

- :class:`DomainError` — business-logic failures. Translate to 4xx at the
  HTTP boundary.
- :class:`InfrastructureError` — plumbing failures (DB, event bus, etc.).
  Propagate as 5xx unless explicitly caught.

Each domain extends ``DomainError`` in its own ``exceptions.py``. Use the
narrowest exception type the call site can usefully react to.

See ``docs/superpowers/specs/2026-05-28-backend-restructure-design.md`` §2.
"""

from __future__ import annotations


class PawrrtalError(Exception):
    """Root of every Pawrrtal-raised exception. Never raised directly."""


class DomainError(PawrrtalError):
    """Business-logic failure. Translates to 4xx at the HTTP boundary."""


class InfrastructureError(PawrrtalError):
    """Plumbing failure (DB, event bus, …). Propagates as 5xx by default."""
