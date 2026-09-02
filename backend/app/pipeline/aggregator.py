"""Concurrent fetch → dedup → persist. DB-driven replacement for ai-podcast's aggregator."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FetchRun, Source, Story as StoryModel
from app.llm import get_provider
from app.llm.probe import check_llm as probe_llm
from app.pipeline.analyzer import analyze_stories
from app.pipeline.health_writer import record_health
from app.pipeline.llm_state import get_outage_state, record_outage, record_probe, clear_outage
from app.pipeline.persist import prune_old, save_stories
from app.sources.base import Story
from app.sources.claude_blog import fetch_claude_blog
from app.sources.hackernews import fetch_hackernews
from app.sources.html_links import fetch_html_links
from app.sources.implicator import fetch_implicator
from app.sources.reddit import fetch_reddit
from app.sources.rss_generic import fetch_rss
from app.sources.techmeme import fetch_techmeme
from app.utils.content_scraper import enrich_stories
from app.utils.dedup import deduplicate

logger = logging.getLogger(__name__)

# source.type → fetcher
FETCHERS = {
    "hackernews_api": fetch_hackernews,
    "rss": fetch_rss,
    "reddit_json": fetch_reddit,
    "claude_blog": fetch_claude_blog,
    "html_links": fetch_html_links,
}

# For type=html_scraper, dispatch by source.key
HTML_SCRAPERS = {
    "techmeme": fetch_techmeme,
    "implicator": fetch_implicator,
}


def source_to_config(src: Source) -> dict:
    cfg: dict = {
        "_source_name": src.name,
        "max_stories": src.max_stories,
    }
    if src.url:
        cfg["url"] = src.url
    if src.keywords:
        try:
            cfg["keywords"] = json.loads(src.keywords)
        except (json.JSONDecodeError, TypeError):
            cfg["keywords"] = []
    if src.min_score is not None:
        cfg["min_score"] = src.min_score
    if src.subreddit:
        cfg["subreddit"] = src.subreddit
    if src.sort:
        cfg["sort"] = src.sort
    if src.extra_config:
        try:
            cfg.update(json.loads(src.extra_config))
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def resolve_fetcher(src: Source):
    if src.type == "html_scraper":
        return HTML_SCRAPERS.get(src.key)
    return FETCHERS.get(src.type)


# While the LLM outage is active, scheduled runs probe at most this often.
PROBE_INTERVAL_S = 3600

# Max unanalyzed stories drained per run once the LLM is back (also caps the
# healthy path — a backlog only exists after an outage or manual backfill).
BACKLOG_LIMIT = 200


async def _should_run_analysis(
    session: AsyncSession,
    *,
    llm_provider: str,
    llm_model: str,
    llm_base_url: str,
    llm_api_key: str,
) -> tuple[bool, str | None]:
    """Outage gate. Returns (allowed, skip_reason).

    Healthy path → (True, None). Outage active → probe (rate-limited to once
    per PROBE_INTERVAL_S): probe ok clears the outage and allows the run;
    probe failed skips analysis this run and bumps skipped_runs.
    """
    state = await get_outage_state(session)
    if state is None:
        return True, None

    last_probe = state.get("last_probe_at")
    if last_probe:
        try:
            elapsed = (
                datetime.now(timezone.utc)
                - datetime.strptime(last_probe, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            ).total_seconds()
            if elapsed < PROBE_INTERVAL_S:
                return False, f"probe rate-limited ({int(PROBE_INTERVAL_S - elapsed)}s left)"
        except ValueError:
            pass  # corrupt timestamp — probe anyway

    ok, reason = await probe_llm(
        provider=llm_provider, model=llm_model,
        base_url=llm_base_url, api_key=llm_api_key,
    )
    if ok:
        await clear_outage(session)
        logger.info("LLM recovered — clearing outage, draining analysis backlog")
        return True, None
    await record_probe(session, ok=False)
    return False, reason


async def _timed_fetch(src: Source, coro):
    t0 = time.monotonic()
    try:
        result = await coro
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return src, result, elapsed_ms, None
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return src, None, elapsed_ms, str(e)


async def run_once(
    session: AsyncSession,
    *,
    only_source_id: int | None = None,
    dry_run: bool = False,
    enrich_content: bool = False,
    retention_days: int | None = None,
    analysis_enabled: bool = False,
    llm_provider: str = "ollama",
    llm_model: str = "llama3.2",
    llm_base_url: str = "",
    llm_api_key: str = "",
) -> FetchRun:
    """Execute one fetch cycle.

    Writes a FetchRun row (started → finished), per-source health rows,
    and any new stories to the DB. Returns the FetchRun.
    """
    started = datetime.now(timezone.utc).isoformat()
    run = FetchRun(started_at=started, status="running")
    session.add(run)
    await session.flush()  # get run.id

    stmt = select(Source).where(Source.enabled == 1)
    if only_source_id is not None:
        stmt = stmt.where(Source.id == only_source_id)
    sources = (await session.execute(stmt)).scalars().all()

    tasks = []
    for src in sources:
        fetcher = resolve_fetcher(src)
        if fetcher is None:
            logger.warning("no fetcher for source key=%s type=%s", src.key, src.type)
            continue
        cfg = source_to_config(src)
        tasks.append(_timed_fetch(src, fetcher(cfg)))

    results = await asyncio.gather(*tasks, return_exceptions=False)

    all_stories: list[tuple[Source, Story]] = []
    sources_ok = 0
    sources_failed = 0

    for src, fetched, elapsed_ms, error in results:
        ok = error is None
        count = len(fetched) if fetched else 0
        record_health(
            session,
            source_id=src.id,
            run_id=run.id,
            ok=ok,
            story_count=count,
            latency_ms=elapsed_ms,
            error=error,
        )
        if ok:
            sources_ok += 1
            logger.info("source %s: %d stories (%dms)", src.key, count, elapsed_ms)
            for story in fetched or []:
                all_stories.append((src, story))
        else:
            sources_failed += 1
            logger.error("source %s failed: %s", src.key, error)

    # Dedup within this batch (cross-run dedup happens in persist.save_stories via UNIQUE index)
    deduped_stories = deduplicate([s for _, s in all_stories])
    # Rebuild the source-association list using object identity
    deduped_keys = {id(s) for s in deduped_stories}
    deduped_pairs = [(src, s) for src, s in all_stories if id(s) in deduped_keys]

    if enrich_content and deduped_stories:
        await enrich_stories(deduped_stories)

    stories_new = 0
    if not dry_run and deduped_pairs:
        stories_new = await save_stories(session, deduped_pairs)

    if analysis_enabled:
        try:
            allowed, skip_reason = await _should_run_analysis(
                session,
                llm_provider=llm_provider, llm_model=llm_model,
                llm_base_url=llm_base_url, llm_api_key=llm_api_key,
            )
            if not allowed:
                logger.warning("LLM analysis skipped this run: %s", skip_reason)
            else:
                # Drain the backlog (capped), not just this run's stories — after an
                # outage the skipped stories would otherwise stay unanalyzed forever.
                unanalyzed = await session.execute(
                    select(StoryModel.id)
                    .where(StoryModel.analyzed_at.is_(None))
                    .order_by(StoryModel.first_seen_at.asc())
                    .limit(BACKLOG_LIMIT)
                )
                new_ids = [row[0] for row in unanalyzed.fetchall()]
                if new_ids:
                    provider = get_provider(
                        provider_name=llm_provider, model=llm_model,
                        base_url=llm_base_url, api_key=llm_api_key,
                    )
                    await analyze_stories(session, new_ids, provider)
                    await session.commit()
                    await clear_outage(session)
        except Exception as e:
            logger.exception("AI analysis failed — stories saved without analysis")
            await record_outage(
                session, reason=f"{type(e).__name__}: {e}"
            )
            await session.commit()

    if retention_days is not None and not dry_run:
        await prune_old(session, retention_days)

    finished = datetime.now(timezone.utc).isoformat()
    run.finished_at = finished
    run.status = "success" if sources_failed == 0 else ("partial" if sources_ok > 0 else "failed")
    run.stories_new = stories_new
    run.stories_seen = len(deduped_stories)
    run.sources_ok = sources_ok
    run.sources_failed = sources_failed
    run.duration_ms = int(
        (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds() * 1000
    )

    await session.commit()
    logger.info(
        "fetch_run id=%d status=%s new=%d seen=%d ok=%d failed=%d duration_ms=%d",
        run.id, run.status, run.stories_new, run.stories_seen,
        run.sources_ok, run.sources_failed, run.duration_ms,
    )
    return run
