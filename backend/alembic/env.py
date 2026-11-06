from __future__ import annotations

from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers tables)
from app.config import get_settings
from app.db import Base, make_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    # Tests pass an explicit URL via config attributes; otherwise use app settings.
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        _run(connectable)
        return
    engine = make_engine(_url())
    with engine.connect() as connection:
        _run(connection)


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Batch mode rebuilds a table (copy, DROP, rename). With foreign keys enforced, the DROP
        # would fire ON DELETE CASCADE / SET NULL on every referencing row and silently wipe
        # data (sub-categories, merchant rules, transaction categories). Enforcement must be
        # off for the migration; the PRAGMA only works outside a transaction.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
        if sqlite:
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise RuntimeError(f"Migration left {len(broken)} broken foreign key reference(s)")
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
