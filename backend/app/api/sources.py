import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Source, Story as StoryModel
from app.pipeline.aggregator import resolve_fetcher, source_to_config
from app.pipeline.persist import save_stories
from app.utils.dedup import normalize_url
from app.utils.image_extractor import fetch_images

router = APIRouter(prefix="/api", tags=["sources"])


class SourceCreate(BaseModel):
    key: str
    name: str
    type: str
    url: str | None = None
    enabled: bool = True
    keywords: list[str] | None = None
    max_stories: int = 5
    min_score: int | None = None
    subreddit: str | None = None
    sort: str | None = None
    extra_config: dict | None = None


class SourceUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    url: str | None = None
    enabled: bool | None = None
    keywords: list[str] | None = None
    max_stories: int | None = None
    min_score: int | None = None
    subreddit: str | None = None
    sort: str | None = None
    extra_config: dict | None = None


def _serialize(src: Source) -> dict:
    kw = None
    if src.keywords:
        try:
            kw = json.loads(src.keywords)
        except (json.JSONDecodeError, TypeError):
            kw = []
    extra = None
    if src.extra_config:
        try:
            extra = json.loads(src.extra_config)
        except (json.JSONDecodeError, TypeError):
            extra = {}
    return {
        "id": src.id,
        "key": src.key,
        "name": src.name,
        "type": src.type,
        "url": src.url,
        "enabled": bool(src.enabled),
        "keywords": kw,
        "max_stories": src.max_stories,
        "min_score": src.min_score,
        "subreddit": src.subreddit,
        "sort": src.sort,
        "extra_config": extra,
        "created_at": src.created_at,
        "updated_at": src.updated_at,
    }


@router.get("/sources")
async def list_sources(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Source).order_by(Source.id))).scalars().all()
    return {"items": [_serialize(r) for r in rows]}


@router.post("/sources", status_code=201)
async def create_source(body: SourceCreate, session: AsyncSession = Depends(get_session)):
    src = Source(
        key=body.key,
        name=body.name,
        type=body.type,
        url=body.url,
        enabled=1 if body.enabled else 0,
        keywords=json.dumps(body.keywords) if body.keywords else None,
        max_stories=body.max_stories,
        min_score=body.min_score,
        subreddit=body.subreddit,
        sort=body.sort,
        extra_config=json.dumps(body.extra_config) if body.extra_config else None,
    )
    session.add(src)
    await session.commit()
    await session.refresh(src)
    return _serialize(src)


@router.put("/sources/{source_id}")
async def update_source(
    source_id: int, body: SourceUpdate, session: AsyncSession = Depends(get_session)
):
    src = await session.get(Source, source_id)
    if not src:
        raise HTTPException(404, "source not found")

    if body.name is not None:
        src.name = body.name
    if body.type is not None:
        src.type = body.type
    if body.url is not None:
        src.url = body.url
    if body.enabled is not None:
        src.enabled = 1 if body.enabled else 0
    if body.keywords is not None:
        src.keywords = json.dumps(body.keywords)
    if body.max_stories is not None:
        src.max_stories = body.max_stories
    if body.min_score is not None:
        src.min_score = body.min_score
    if body.subreddit is not None:
        src.subreddit = body.subreddit
    if body.sort is not None:
        src.sort = body.sort
    if body.extra_config is not None:
        src.extra_config = json.dumps(body.extra_config)

    src.updated_at = datetime.now(timezone.utc).isoformat()
    await session.commit()
    await session.refresh(src)
    return _serialize(src)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: int, session: AsyncSession = Depends(get_session)):
    src = await session.get(Source, source_id)
    if not src:
        raise HTTPException(404, "source not found")
    await session.delete(src)
    await session.commit()


@router.post("/sources/{source_id}/reconcile")
async def reconcile_source(
    source_id: int, session: AsyncSession = Depends(get_session)
):
    src = await session.get(Source, source_id)
    if not src:
        raise HTTPException(404, "source not found")

    fetcher = resolve_fetcher(src)
    if not fetcher:
        raise HTTPException(400, f"no fetcher for source type={src.type}")

    cfg = source_to_config(src)
    cfg["max_stories"] = max(cfg.get("max_stories", 5) * 5, 50)
    cfg["min_score"] = 0
    cfg["skip_keyword_filter"] = True

    try:
        available = await fetcher(cfg)
    except Exception as e:
        raise HTTPException(502, f"fetch failed: {e}")

    result = await session.execute(
        select(StoryModel.url_normalized, StoryModel.title, StoryModel.url).where(
            StoryModel.source_id == source_id
        )
    )
    existing_norms = {}
    for row in result:
        existing_norms[row[0]] = {"title": row[1], "url": row[2]}

    matched = []
    missing = []
    for story in available:
        norm = normalize_url(story.url)
        if norm in existing_norms:
            matched.append(
                {
                    "title": story.title,
                    "url": story.url,
                    "db_title": existing_norms[norm]["title"],
                }
            )
        else:
            missing.append({"title": story.title, "url": story.url})

    return {
        "source_id": source_id,
        "source_name": src.name,
        "available_count": len(available),
        "matched_count": len(matched),
        "missing_count": len(missing),
        "matched": matched,
        "missing": missing,
    }


@router.post("/sources/{source_id}/reconcile/import")
async def reconcile_import(
    source_id: int, session: AsyncSession = Depends(get_session)
):
    src = await session.get(Source, source_id)
    if not src:
        raise HTTPException(404, "source not found")

    fetcher = resolve_fetcher(src)
    if not fetcher:
        raise HTTPException(400, f"no fetcher for source type={src.type}")

    cfg = source_to_config(src)
    cfg["max_stories"] = max(cfg.get("max_stories", 5) * 5, 50)
    cfg["min_score"] = 0
    cfg["skip_keyword_filter"] = True

    try:
        available = await fetcher(cfg)
    except Exception as e:
        raise HTTPException(502, f"fetch failed: {e}")

    result = await session.execute(
        select(StoryModel.url_normalized).where(StoryModel.source_id == source_id)
    )
    existing = {row[0] for row in result}

    missing_stories = [s for s in available if normalize_url(s.url) not in existing]
    if not missing_stories:
        return {
            "source_id": source_id,
            "source_name": src.name,
            "available_count": len(available),
            "imported": 0,
        }

    await fetch_images(missing_stories)
    pairs = [(src, s) for s in missing_stories]
    inserted = await save_stories(session, pairs)
    await session.commit()

    return {
        "source_id": source_id,
        "source_name": src.name,
        "available_count": len(available),
        "imported": inserted,
    }
