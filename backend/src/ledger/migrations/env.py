from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from ledger import models  # noqa: F401  (register tables)
from ledger.db import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite needs batch mode for ALTERs
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
