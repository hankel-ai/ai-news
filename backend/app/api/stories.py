import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
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
    sort_by: str = "relevance",
    min_score: int | None = None,
    topics: str | None = None,
    unread_only: bool = False,
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
    if min_score is not None:
        stmt = stmt.where(Story.relevance_score >= min_score)
        count_stmt = count_stmt.where(Story.relevance_score >= min_score)
    if topics:
        topic_list = [t.strip() for t in topics.split(",")]
        for topic in topic_list:
            stmt = stmt.where(Story.topics.like(f'%"{topic}"%'))
            count_stmt = count_stmt.where(Story.topics.like(f'%"{topic}"%'))
    if unread_only:
        stmt = stmt.where(Story.viewed_at.is_(None))
        count_stmt = count_stmt.where(Story.viewed_at.is_(None))

    total = (await session.execute(count_stmt)).scalar_one()

    if sort_by == "relevance":
        stmt = stmt.order_by(Story.relevance_score.desc().nulls_last(), Story.first_seen_at.desc())
    elif sort_by == "newest":
        stmt = stmt.order_by(Story.first_seen_at.desc())
    elif sort_by == "source":
        stmt = stmt.order_by(Story.source_name, Story.relevance_score.desc().nulls_last())
    else:
        stmt = stmt.order_by(Story.first_seen_at.desc())

    stmt = stmt.offset(offset).limit(limit)

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
                "viewed_at": r.viewed_at,
                "ai_summary": r.ai_summary,
                "relevance_score": r.relevance_score,
                "topics": json.loads(r.topics) if r.topics else [],
                "analyzed_at": r.analyzed_at,
            }
            for r in rows
        ],
    }


@router.put("/stories/{story_id}/view")
async def mark_viewed(story_id: int, session: AsyncSession = Depends(get_session)):
    story = await session.get(Story, story_id)
    if not story:
        raise HTTPException(404, "story not found")
    if not story.viewed_at:
        story.viewed_at = datetime.now(timezone.utc).isoformat()
        await session.commit()
    return {"id": story.id, "viewed_at": story.viewed_at}


_STRIP_HEADERS = {
    "x-frame-options",
    "content-security-policy",
    "content-security-policy-report-only",
}

_PROXY_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


@router.get("/proxy")
async def proxy_page(url: str = Query(...)):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Invalid URL scheme")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"User-Agent": _PROXY_UA},
                follow_redirects=True,
                timeout=15,
            )
    except Exception as e:
        logger.warning("proxy fetch failed for %s: %s", url, e)
        raise HTTPException(502, "Failed to fetch page")

    content_type = resp.headers.get("content-type", "text/html")
    out_headers = {}
    for k, v in resp.headers.items():
        if k.lower() not in _STRIP_HEADERS:
            out_headers[k] = v
    out_headers.pop("transfer-encoding", None)
    out_headers.pop("content-encoding", None)
    out_headers.pop("content-length", None)

    body = resp.content
    if "text/html" in content_type:
        base_tag = f'<base href="{url}">'
        text = resp.text
        head_match = re.search(r"<head[^>]*>", text, re.IGNORECASE)
        if head_match:
            insert_pos = head_match.end()
            text = text[:insert_pos] + base_tag + text[insert_pos:]
        else:
            text = base_tag + text
        body = text.encode("utf-8", errors="replace")

    return Response(
        content=body,
        status_code=resp.status_code,
        headers=out_headers,
        media_type=content_type,
    )
