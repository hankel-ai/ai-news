"""Write fetched stories to the database, handling dedup via UNIQUE(url_normalized)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SeenUrl, Source
from app.db.models import Story as StoryModel
from app.sources.base import Story
from app.utils.article_date import date_from_url
from app.utils.dedup import normalize_url

logger = logging.getLogger(__name__)


async def save_stories(
    session: AsyncSession,
    pairs: list[tuple[Source, Story]],
) -> int:
    """Persist stories. Returns the count of newly inserted rows.

    Checks for existing url_normalized before inserting to avoid breaking
    the session with UNIQUE constraint violations. Also checks the seen_urls
    ledger, which outlives prune_old() — otherwise any article still linked
    from its source's index page comes back as new every retention_days.
    """
    norms = [normalize_url(s.url) for _, s in pairs]
    existing = set()
    if norms:
        result = await session.execute(
            select(StoryModel.url_normalized).where(
                StoryModel.url_normalized.in_(norms)
            )
        )
        existing = {row[0] for row in result}
        result = await session.execute(
            select(SeenUrl.url_normalized).where(SeenUrl.url_normalized.in_(norms))
        )
        existing |= {row[0] for row in result}

    inserted = 0
    for src, story in pairs:
        norm = normalize_url(story.url)
        if norm in existing:
            continue
        existing.add(norm)
        now = datetime.now(timezone.utc).isoformat()
        session.add(SeenUrl(url_normalized=norm, first_seen_at=now))
        row = StoryModel(
            source_id=src.id,
            title=story.title,
            url=story.url,
            url_normalized=norm,
            source_name=story.source_name,
            summary=story.summary or None,
            article_content=story.article_content or None,
            score=story.score,
            published_at=story.published.isoformat() if story.published else None,
            keywords_matched=json.dumps(story.keywords_matched) if story.keywords_matched else None,
            first_seen_at=now,
        )
        session.add(row)
        inserted += 1

    if inserted:
        await session.flush()
    return inserted


async def backfill_url_dates(session: AsyncSession) -> int:
    """Fill published_at for stored stories whose URL encodes a date.

    Rows ingested before dates were extracted still date by first_seen_at, so a
    months-old digest keeps reading as today's news until it ages out. Idempotent:
    once a row has a date it is no longer a candidate. Cheap enough to run at
    every startup — it only ever scans rows that are still NULL.
    """
    rows = (
        await session.execute(
            select(StoryModel).where(StoryModel.published_at.is_(None))
        )
    ).scalars().all()

    updated = 0
    for row in rows:
        dt = date_from_url(row.url)
        if dt is None:
            continue
        row.published_at = dt.isoformat()
        updated += 1

    if updated:
        await session.commit()
        logger.info("backfilled publication dates for %d stories", updated)
    return updated


async def prune_old(session: AsyncSession, retention_days: int) -> int:
    """Delete stories older than retention_days. Returns count deleted.

    Deliberately leaves seen_urls intact: the ledger is what stops a pruned
    story from being re-ingested as new on the next fetch.
    """
    result = await session.execute(
        delete(StoryModel).where(
            StoryModel.first_seen_at < text(f"datetime('now', '-{int(retention_days)} days')")
        )
    )
    count = result.rowcount
    if count:
        logger.info("pruned %d stories older than %d days", count, retention_days)
    return count
