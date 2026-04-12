from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import FetchRun, Setting, SourceHealth
from app.scheduler import get_scheduler

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    scheduler = get_scheduler()
    scheduler_running = scheduler is not None and scheduler.running

    last_run_row = (
        await session.execute(
            select(FetchRun).order_by(FetchRun.started_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    last_run = None
    if last_run_row:
        last_run = {
            "id": last_run_row.id,
            "finished_at": last_run_row.finished_at,
            "status": last_run_row.status,
        }

    interval_row = (
        await session.execute(
            select(Setting.value).where(Setting.key == "fetch_interval_minutes")
        )
    ).scalar_one_or_none()
    interval = int(interval_row) if interval_row else 60

    status = "ok" if db_ok and scheduler_running else "degraded"

    return {
        "status": status,
        "db": "ok" if db_ok else "error",
        "scheduler": "running" if scheduler_running else "stopped",
        "last_fetch": last_run,
        "interval_minutes": interval,
    }


@router.get("/fetch-runs")
async def list_fetch_runs(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(FetchRun).order_by(FetchRun.started_at.desc()).limit(limit)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "status": r.status,
                "stories_new": r.stories_new,
                "stories_seen": r.stories_seen,
                "sources_ok": r.sources_ok,
                "sources_failed": r.sources_failed,
                "duration_ms": r.duration_ms,
                "error": r.error,
            }
            for r in rows
        ]
    }


@router.get("/source-health")
async def source_health_stats(
    source_id: int | None = None,
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    cutoff = func.datetime("now", f"-{days} days")
    stmt = select(
        SourceHealth.source_id,
        func.count().label("total"),
        func.sum(SourceHealth.ok).label("successes"),
        func.avg(SourceHealth.latency_ms).label("avg_latency_ms"),
        func.avg(SourceHealth.story_count).label("avg_stories"),
    ).where(SourceHealth.fetched_at >= cutoff).group_by(SourceHealth.source_id)

    if source_id is not None:
        stmt = stmt.where(SourceHealth.source_id == source_id)

    rows = (await session.execute(stmt)).all()
    items = []
    for row in rows:
        total = row.total or 1
        successes = row.successes or 0
        rate = successes / total
        if rate >= 0.85:
            status = "healthy"
        elif rate >= 0.50:
            status = "degraded"
        else:
            status = "broken"
        items.append({
            "source_id": row.source_id,
            "total_fetches": total,
            "successes": successes,
            "success_rate": round(rate, 3),
            "avg_latency_ms": round(row.avg_latency_ms or 0),
            "avg_stories": round(row.avg_stories or 0, 1),
            "status": status,
        })
    return {"items": items}
