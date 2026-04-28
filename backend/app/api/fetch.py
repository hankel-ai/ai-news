import logging
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
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


@router.post("/llm/ping")
async def llm_ping(session: AsyncSession = Depends(get_session)):
    """Quick LLM connectivity check — sends a 3-token prompt and returns timing."""
    llm_provider = await _get_setting(session, "llm_provider", "ollama")
    llm_model = await _get_setting(session, "llm_model", "llama3.2")
    llm_base_url = await _get_setting(session, "llm_base_url", "")
    llm_api_key = await _get_setting(session, "llm_api_key", "")

    provider = get_provider(
        provider_name=llm_provider, model=llm_model,
        base_url=llm_base_url, api_key=llm_api_key,
    )
    t0 = time.monotonic()
    try:
        reply = await provider.complete("Reply with just OK.", system="")
    except Exception as e:
        return {
            "ok": False,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "error": f"{type(e).__name__}: {e}",
        }
    return {
        "ok": True,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "model": llm_model,
        "reply": reply.strip()[:200],
    }


@router.post("/analyze")
async def trigger_analyze(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Analyze the next batch of unanalyzed stories. Caller polls until remaining=0."""
    llm_provider = await _get_setting(session, "llm_provider", "ollama")
    llm_model = await _get_setting(session, "llm_model", "llama3.2")
    llm_base_url = await _get_setting(session, "llm_base_url", "")
    llm_api_key = await _get_setting(session, "llm_api_key", "")

    result = await session.execute(
        select(Story.id).where(Story.analyzed_at.is_(None)).limit(limit)
    )
    batch_ids = [row[0] for row in result.fetchall()]

    if not batch_ids:
        return {"analyzed": 0, "remaining": 0, "duration_ms": 0, "ok": True}

    provider = get_provider(
        provider_name=llm_provider, model=llm_model,
        base_url=llm_base_url, api_key=llm_api_key,
    )
    t0 = time.monotonic()
    try:
        await analyze_stories(session, batch_ids, provider)
        await session.commit()
    except Exception as e:
        logger.exception("manual /api/analyze failed")
        remaining = (await session.execute(
            select(func.count(Story.id)).where(Story.analyzed_at.is_(None))
        )).scalar_one()
        return {
            "analyzed": 0, "remaining": int(remaining),
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "ok": False, "error": f"{type(e).__name__}: {e}",
        }

    remaining = (await session.execute(
        select(func.count(Story.id)).where(Story.analyzed_at.is_(None))
    )).scalar_one()
    return {
        "analyzed": len(batch_ids),
        "remaining": int(remaining),
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "ok": True,
    }
