"""Small, idempotent schema upgrades for existing SQLite databases.

The project intentionally avoids a migration framework: the schema is created
by ``Base.metadata.create_all`` and this module only adds columns that were
introduced after a database was first created. Every statement is safe to run
on every startup, and works on SQLite (the local default) and PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .database import Base


def ensure_schema(engine: Engine) -> list[str]:
    """Create missing tables and add columns that predate the current model.

    Returns the list of changes applied, which is logged at startup so it is
    obvious when an existing database was upgraded.
    """
    Base.metadata.create_all(bind=engine)

    applied: list[str] = []
    inspector = inspect(engine)
    if "topics" not in inspector.get_table_names():
        return applied

    columns = {column["name"] for column in inspector.get_columns("topics")}
    with engine.begin() as connection:
        if "subject_id" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE topics ADD COLUMN subject_id INTEGER "
                    "REFERENCES subjects(id)"
                )
            )
            applied.append("topics.subject_id")
        if "source" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE topics ADD COLUMN source VARCHAR(60) "
                    "DEFAULT 'curated'"
                )
            )
            applied.append("topics.source")
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_topics_subject_id ON topics (subject_id)")
        )

    return applied
