"""Alembic environment configuration for pawrrtal backend migrations."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from app.core.config import settings

# Stable advisory-lock id so concurrent `alembic upgrade head` invocations
# (e.g. Railway rolling deploys booting two replicas at once) serialise
# instead of racing on schema mutation. Postgres-only; ignored on SQLite.
ALEMBIC_MIGRATION_LOCK_ID = 0xA1EBAB1C

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
config.set_main_option("sqlalchemy.url", settings.db_url_sync)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import metadata from the app models so autogenerate can detect changes.
from app.db_base import Base
from app import models  # noqa: F401  — registers all ORM models

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well. By skipping the Engine creation we don't
    even need a DBAPI to be available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection
    with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_postgres = connection.dialect.name == "postgresql"
        if is_postgres:
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": ALEMBIC_MIGRATION_LOCK_ID},
            )
        try:
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
        finally:
            if is_postgres:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": ALEMBIC_MIGRATION_LOCK_ID},
                )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
