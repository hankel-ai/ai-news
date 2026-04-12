"""APScheduler wrapper — schedules the fetch job and supports live rescheduling."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import SessionLocal
from app.db.models import Setting
from app.pipeline.aggregator import run_once

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

FETCH_JOB_ID = "fetch_job"
PRUNE_JOB_ID = "prune_job"


async def _get_setting(session: AsyncSession, key: str, default: str) -> str:
    result = await session.execute(select(Setting.value).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row if row is not None else default


async def _run_fetch_job() -> None:
    async with SessionLocal() as session:
        enrich_raw = await _get_setting(session, "enrich_content", "false")
        enrich = enrich_raw.strip().lower() in ("true", "1", "yes")
        retention_raw = await _get_setting(session, "retention_days", "30")
        try:
            retention = int(retention_raw)
        except ValueError:
            retention = 30
        await run_once(session, enrich_content=enrich, retention_days=retention)


def init_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    return _scheduler


async def start_scheduler(interval_minutes: int = 60) -> None:
    if _scheduler is None:
        raise RuntimeError("call init_scheduler() first")

    _scheduler.add_job(
        _run_fetch_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=FETCH_JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("scheduler started: fetch every %d minutes", interval_minutes)


async def reschedule_from_db() -> int:
    """Re-read fetch_interval_minutes from DB and reschedule. Returns new interval."""
    async with SessionLocal() as session:
        raw = await _get_setting(session, "fetch_interval_minutes", "60")
        try:
            interval = int(raw)
        except ValueError:
            interval = 60

    if _scheduler and _scheduler.get_job(FETCH_JOB_ID):
        _scheduler.reschedule_job(
            FETCH_JOB_ID,
            trigger=IntervalTrigger(minutes=interval),
        )
        logger.info("rescheduled fetch_job: every %d minutes", interval)
    return interval


def shutdown_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler shut down")


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler
