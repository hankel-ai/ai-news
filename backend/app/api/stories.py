import asyncio
import logging

import httpx
import trafilatura
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Story

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["stories"])


@router.get("/stories")
async def list_stories(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Story)
    count_stmt = select(func.count(Story.id))

    if source_id is not None:
        stmt = stmt.where(Story.source_id == source_id)
        count_stmt = count_stmt.where(Story.source_id == source_id)
    if since:
        stmt = stmt.where(func.coalesce(Story.published_at, Story.first_seen_at) >= since)
        count_stmt = count_stmt.where(func.coalesce(Story.published_at, Story.first_seen_at) >= since)
    if until:
        stmt = stmt.where(func.coalesce(Story.published_at, Story.first_seen_at) <= until)
        count_stmt = count_stmt.where(func.coalesce(Story.published_at, Story.first_seen_at) <= until)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(Story.title.ilike(pattern) | Story.summary.ilike(pattern))
        count_stmt = count_stmt.where(Story.title.ilike(pattern) | Story.summary.ilike(pattern))

    total = (await session.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Story.first_seen_at.desc()).offset(offset).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "source_id": r.source_id,
                "source_name": r.source_name,
                "summary": r.summary,
                "score": r.score,
                "published_at": r.published_at,
                "first_seen_at": r.first_seen_at,
                "keywords_matched": r.keywords_matched,
                "image_url": r.image_url,
            }
            for r in rows
        ],
    }


_CONTENT_LIMIT = 15000


@router.get("/stories/{story_id}/content")
async def get_story_content(
    story_id: int,
    session: AsyncSession = Depends(get_session),
):
    story = await session.get(Story, story_id)
    if not story:
        raise HTTPException(404, "Story not found")

    if story.article_content:
        return {"content": story.article_content, "url": story.url}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(headers=headers) as client:
            resp = await client.get(story.url, follow_redirects=True, timeout=15)
            resp.raise_for_status()
        html = resp.text
        text = await asyncio.to_thread(
            trafilatura.extract,
            html,
            include_comments=False,
            include_tables=True,
            include_links=True,
            output_format="html",
        )
        content = (text or "")[:_CONTENT_LIMIT]
    except Exception as e:
        logger.warning("content fetch failed for story %d: %s", story_id, e)
        content = ""

    if content:
        story.article_content = content
        await session.commit()

    return {"content": content, "url": story.url}
