from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.pipeline.aggregator import run_once

router = APIRouter(prefix="/api", tags=["fetch"])


@router.post("/fetch")
async def trigger_fetch(
    source_id: int | None = Query(None),
    dry_run: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    run = await run_once(session, only_source_id=source_id, dry_run=dry_run)
    return {
        "id": run.id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "stories_new": run.stories_new,
        "stories_seen": run.stories_seen,
        "sources_ok": run.sources_ok,
        "sources_failed": run.sources_failed,
        "duration_ms": run.duration_ms,
    }
