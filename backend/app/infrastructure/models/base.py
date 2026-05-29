"""Declarative base for SQLAlchemy ORM models.

Lives in its own module so that the database session layer, fastapi-users
``User`` model, and the domain table modules can all import ``Base``
without forming an import cycle.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass
