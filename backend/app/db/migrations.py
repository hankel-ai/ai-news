"""Forward-only SQL migrations runner for SQLite.

Each file in migrations_sql/ is a monotonically-versioned batch.
Files are named `NNN_description.sql` and applied in sorted order exactly once.
The `schema_version` table records which versions have been applied.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.engine import engine as _default_engine

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations_sql"
_FILENAME_RE = re.compile(r"^(\d+)_.*\.sql$")


def _discover() -> list[tuple[int, Path]]:
    items: list[tuple[int, Path]] = []
    for p in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        m = _FILENAME_RE.match(p.name)
        if not m:
            continue
        items.append((int(m.group(1)), p))
    items.sort(key=lambda x: x[0])
    return items


async def run(engine: AsyncEngine | None = None) -> None:
    """Apply any pending migrations. Idempotent."""
    engine = engine or _default_engine
    async with engine.begin() as conn:
        # WAL + FK must be set before any other work.
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )

        result = await conn.execute(text("SELECT version FROM schema_version"))
        applied = {row[0] for row in result}

        for version, path in _discover():
            if version in applied:
                continue
            logger.info("applying migration %s", path.name)
            sql = path.read_text(encoding="utf-8")
            # aiosqlite's execute() only handles one statement at a time,
            # so split on semicolons and run each individually.
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.exec_driver_sql(stmt)
            await conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :t)"),
                {"v": version, "t": datetime.now(timezone.utc).isoformat()},
            )
    logger.info("migrations complete")
