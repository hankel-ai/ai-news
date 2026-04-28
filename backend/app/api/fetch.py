import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Setting, Story
from app.llm import get_provider
from app.pipeline.aggregator import run_once
from app.pipeline.analyzer import analyze_stories

logger = logging.getLogger(__name__)

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


async def _get_setting(session: AsyncSession, key: str, default: str) -> str:
    result = await session.execute(select(Setting.value).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row if row is not None else default


@router.post("/analyze")
async def trigger_analyze(session: AsyncSession = Depends(get_session)):
    """Manually trigger AI analysis on all unanalyzed stories."""
    llm_provider = await _get_setting(session, "llm_provider", "ollama")
    llm_model = await _get_setting(session, "llm_model", "llama3.2")
    llm_base_url = await _get_setting(session, "llm_base_url", "")
    llm_api_key = await _get_setting(session, "llm_api_key", "")

    result = await session.execute(
        select(Story.id).where(Story.analyzed_at.is_(None)).limit(200)
    )
    unanalyzed_ids = [row[0] for row in result.fetchall()]

    if not unanalyzed_ids:
        return {"analyzed": 0, "message": "No unanalyzed stories found"}

    provider = get_provider(
        provider_name=llm_provider, model=llm_model,
        base_url=llm_base_url, api_key=llm_api_key,
    )
    try:
        await analyze_stories(session, unanalyzed_ids, provider)
        await session.commit()
    except Exception as e:
        logger.exception("manual /api/analyze failed")
        return {"analyzed": 0, "error": f"{type(e).__name__}: {e}"}

    return {"analyzed": len(unanalyzed_ids), "message": f"Analyzed {len(unanalyzed_ids)} stories"}
