"""CRUD-domain exceptions: missing-row + integrity failures.

Used by the conversations / chat-message CRUD layer; eventually each
domain owns its own ``exceptions.py`` per the restructure plan.
"""

from __future__ import annotations

from app.exceptions import DomainError


class ConversationNotFoundError(DomainError):
    """The requested conversation doesn't exist or isn't visible to this user."""
