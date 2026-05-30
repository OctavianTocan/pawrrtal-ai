"""Infrastructure-domain exceptions: plumbing failures.

These propagate as 5xx at the HTTP boundary by default. Catch the narrowest
variant possible; ``InfrastructureError`` itself is a catch-all for
"something below the application layer broke."
"""

from __future__ import annotations

from app.exceptions import InfrastructureError


class DatabaseError(InfrastructureError):
    """SQLAlchemy / DB failure. Replaces the broad ``SQLAlchemyError`` catch sites."""


class EventBusError(InfrastructureError):
    """Event bus subscriber or publisher broke the bus in a way callers care about."""
