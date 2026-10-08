"""Connection pool and the migration runner."""
import logging
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

log = logging.getLogger("ashwheelz.db")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_MIGRATION_LOCK_ID = 727_274_001

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=settings.db_pool_max,
    # prepare_threshold=None: no server-side prepared statements, which
    # transaction poolers in front of hosted Postgres may not support.
    kwargs={"row_factory": dict_row, "prepare_threshold": None},
    open=False,
)


def run_migrations() -> None:
    """Apply every migrations/*.sql file not yet recorded, in name order.

    An advisory lock keeps two app instances from migrating at once.
    """
    with psycopg.connect(settings.migration_database_url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_ID,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY,"
                " applied_at timestamptz NOT NULL DEFAULT now())"
            )
            applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in applied:
                    continue
                log.info("Applying migration %s", path.name)
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_ID,))
