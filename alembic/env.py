"""Alembic environment — async, reuses app.database's engine (no re-derived URL).

The asyncpg driver + sslmode stripping + SSL context all live in app.database;
we import its `engine`/`Base` so migrations run through the exact same seam the app
uses. `import geoalchemy2` makes Geometry columns render in autogenerate, and
`import app.models` registers every table on Base.metadata.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from alembic import context

import geoalchemy2  # noqa: F401 — so geoalchemy2.Geometry columns render

from app.database import engine, ASYNC_DATABASE_URL, Base
import app.models  # noqa: F401 — registers every table on Base.metadata

# Alembic Config object (reads alembic.ini values, mainly for logging).
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS-managed objects Alembic must never create/drop.
EXCLUDED_TABLES = {"spatial_ref_sys"}
EXCLUDED_SCHEMAS = {"tiger", "topology"}


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name not in EXCLUDED_SCHEMAS
    return True


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name in EXCLUDED_TABLES:
        return False
    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Reuse app.database.engine (async) for online migrations."""
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    """Emit SQL to stdout using the same URL app.database derived."""
    context.configure(
        url=ASYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
