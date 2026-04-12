"""Write fetched stories to the database, handling dedup via UNIQUE(url_normalized)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Source
from app.db.models import Story as StoryModel
from app.sources.base import Story
from app.utils.dedup import normalize_url

logger = logging.getLogger(__name__)


async def save_stories(
    session: AsyncSession,
    pairs: list[tuple[Source, Story]],
) -> int:
    """Persist stories. Returns the count of newly inserted rows.

    Checks for existing url_normalized before inserting to avoid breaking
    the session with UNIQUE constraint violations.
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

    inserted = 0
    for src, story in pairs:
        norm = normalize_url(story.url)
        if norm in existing:
            continue
        existing.add(norm)
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
            image_url=story.image_url,
            first_seen_at=datetime.now(timezone.utc).isoformat(),
        )
        session.add(row)
        inserted += 1

    if inserted:
        await session.flush()
    return inserted


async def prune_old(session: AsyncSession, retention_days: int) -> int:
    """Delete stories older than retention_days. Returns count deleted."""
    result = await session.execute(
        delete(StoryModel).where(
            StoryModel.first_seen_at < text(f"datetime('now', '-{int(retention_days)} days')")
        )
    )
    count = result.rowcount
    if count:
        logger.info("pruned %d stories older than %d days", count, retention_days)
    return count
