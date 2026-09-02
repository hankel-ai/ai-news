import logging
import time

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Setting, Story
from app.llm import get_provider
from app.pipeline.aggregator import run_once
from app.pipeline.analyzer import analyze_stories
from app.pipeline.llm_state import get_outage_state, clear_outage
from app.scheduler import _fetch_job_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["fetch"])


@router.post("/fetch")
async def trigger_fetch(
    source_id: int | None = Query(None),
    dry_run: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    run = await run_once(
        session,
        only_source_id=source_id,
        dry_run=dry_run,
        **await _fetch_job_settings(session),
    )
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


def _default_base_url(provider: str) -> str:
    if provider == "ollama":
        return "http://localhost:11434"
    if provider == "anthropic":
        return "https://api.anthropic.com"
    return ""


def _provider_endpoint(provider: str, base_url: str) -> str:
    base = base_url.rstrip("/")
    if provider == "ollama":
        return f"{base}/api/chat"
    if provider == "anthropic":
        return f"{base or 'https://api.anthropic.com'}/v1/messages"
    if provider == "litellm":
        return f"{base}/v1/chat/completions"
    return base


async def _list_ollama_models(base_url: str) -> list[str] | None:
    if not base_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            return [m.get("name") for m in r.json().get("models", []) if m.get("name")]
    except Exception:
        return None


@router.get("/llm/status")
async def llm_status(session: AsyncSession = Depends(get_session)):
    """LLM outage state for the frontend banner. No LLM call — reads the persisted state row."""
    state = await get_outage_state(session)
    analysis_raw = await _get_setting(session, "analysis_enabled", "true")
    analysis_enabled = analysis_raw.strip().lower() in ("true", "1", "yes")
    if state is None:
        return {
            "outage": False,
            "since": None,
            "reason": None,
            "last_probe_at": None,
            "skipped_runs": 0,
            "analysis_enabled": analysis_enabled,
        }
    return {
        "outage": True,
        "since": state.get("since"),
        "reason": state.get("reason"),
        "last_probe_at": state.get("last_probe_at"),
        "skipped_runs": state.get("skipped_runs", 0),
        "analysis_enabled": analysis_enabled,
    }


@router.post("/llm/ping")
async def llm_ping(session: AsyncSession = Depends(get_session)):
    """Quick LLM connectivity check — sends a tiny prompt and returns timing + endpoint details."""
    llm_provider = await _get_setting(session, "llm_provider", "ollama")
    llm_model = await _get_setting(session, "llm_model", "llama3.2")
    llm_base_url = await _get_setting(session, "llm_base_url", "")
    llm_api_key = await _get_setting(session, "llm_api_key", "")

    effective_base = llm_base_url or _default_base_url(llm_provider)
    endpoint = _provider_endpoint(llm_provider, effective_base)

    result: dict = {
        "ok": False,
        "provider": llm_provider,
        "model": llm_model,
        "base_url": effective_base,
        "endpoint": endpoint,
        "duration_ms": 0,
    }

    try:
        provider = get_provider(
            provider_name=llm_provider, model=llm_model,
            base_url=llm_base_url, api_key=llm_api_key,
        )
    except ValueError as e:
        result["error_type"] = "ConfigError"
        result["error"] = str(e)
        return result

    t0 = time.monotonic()
    try:
        reply = await provider.complete("Reply with just OK.", system="")
    except httpx.HTTPStatusError as e:
        result["duration_ms"] = int((time.monotonic() - t0) * 1000)
        result["error_type"] = "HTTPStatusError"
        result["http_status"] = e.response.status_code
        body = (e.response.text or "")[:500]
        result["error"] = f"HTTP {e.response.status_code}: {body or e.response.reason_phrase}"
        if llm_provider == "ollama":
            result["available_models"] = await _list_ollama_models(effective_base)
        return result
    except httpx.HTTPError as e:
        result["duration_ms"] = int((time.monotonic() - t0) * 1000)
        result["error_type"] = type(e).__name__
        result["error"] = str(e) or repr(e)
        if llm_provider == "ollama":
            result["available_models"] = await _list_ollama_models(effective_base)
        return result
    except Exception as e:
        result["duration_ms"] = int((time.monotonic() - t0) * 1000)
        result["error_type"] = type(e).__name__
        result["error"] = str(e) or repr(e)
        if llm_provider == "ollama":
            result["available_models"] = await _list_ollama_models(effective_base)
        return result

    result["ok"] = True
    result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    result["reply"] = reply.strip()[:200]
    # A successful live call contradicts any recorded outage — clear it (banner's "Check now").
    state = await get_outage_state(session)
    if state is not None:
        await clear_outage(session)
        await session.commit()
        result["outage_cleared"] = True
    return result


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
