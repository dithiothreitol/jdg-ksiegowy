"""Srodowisko Alembic: polaczenie przekazane z `registry.db.upgrade` albo z settings."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, create_engine

from jdg_ksiegowy.registry.db import Base

config = context.config


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite: ALTER przez kopie tabeli
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:  # `alembic revision --autogenerate` z linii polecen
    from jdg_ksiegowy.config import settings

    with create_engine(settings.db_url).begin() as conn:
        _run(conn)
