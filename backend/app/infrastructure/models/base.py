"""Declarative base for SQLAlchemy ORM models.

Lives in its own module so that `app.db` (engine + session factory + the
fastapi-users `User` model) and `app.models` (every other ORM class) can
both import `Base` without forming an import cycle. Prior to this split
`models.py` imported `Base` from `db.py` while `db.py` lazy-imported
`app.models` inside `create_db_and_tables()` to register every ORM class
with `Base.metadata` — a static SCC that pinned sentrux's acyclicity
score to 5000/10000.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass
