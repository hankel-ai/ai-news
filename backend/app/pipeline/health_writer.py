"""Write per-source health rows to the database."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceHealth


def record_health(
    session: AsyncSession,
    *,
    source_id: int,
    run_id: int,
    ok: bool,
    story_count: int,
    latency_ms: int,
    error: str | None = None,
) -> None:
    """Add a SourceHealth row (batched with the session's commit)."""
    row = SourceHealth(
        source_id=source_id,
        run_id=run_id,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        ok=1 if ok else 0,
        story_count=story_count,
        latency_ms=latency_ms,
        error=error,
    )
    session.add(row)
