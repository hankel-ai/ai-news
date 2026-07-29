import asyncio
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Source, Story as StoryModel
from app.pipeline.aggregator import resolve_fetcher, source_to_config
from app.pipeline.persist import save_stories
from app.utils.dedup import normalize_url

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


class DetectFeedRequest(BaseModel):
    url: str


_DETECT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_FEED_PROBE_PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml"]
_FEED_CONTENT_HINTS = ("xml", "rss", "atom")


async def _probe_feed(client: httpx.AsyncClient, candidate: str) -> dict | None:
    """HEAD-or-GET-then-sniff a candidate feed URL. Returns descriptor or None."""
    try:
        resp = await client.get(candidate, follow_redirects=True, timeout=8)
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    ctype = resp.headers.get("content-type", "").lower()
    body_head = resp.text[:512].lower()
    looks_feedy = (
        any(h in ctype for h in _FEED_CONTENT_HINTS)
        or "<rss" in body_head
        or "<feed" in body_head
    )
    if not looks_feedy:
        return None
    return {"url": str(resp.url), "content_type": ctype or "unknown"}


@router.post("/sources/detect-feed")
async def detect_feed(body: DetectFeedRequest):
    """Probe a URL for an RSS/Atom feed; if none found, suggest an html_links config."""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    result: dict = {
        "requested_url": url,
        "feeds": [],
        "fallback": None,
        "error": None,
    }

    async with httpx.AsyncClient(headers={"User-Agent": _DETECT_UA}, timeout=10) as client:
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            result["error"] = f"{type(e).__name__}: {e}"
            return result

        final_url = str(resp.url)
        result["resolved_url"] = final_url

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. <link rel="alternate" type="application/rss+xml|atom+xml">
        for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
            ltype = (link.get("type") or "").lower()
            href = link.get("href", "").strip()
            if not href:
                continue
            if "rss" in ltype or "atom" in ltype:
                result["feeds"].append({
                    "url": urljoin(final_url, href),
                    "title": link.get("title", "") or "Feed",
                    "type": ltype,
                    "source": "link-alternate",
                })

        # 2. Probe common feed paths under the site root, in parallel
        if not result["feeds"]:
            parsed = urlparse(final_url)
            root = f"{parsed.scheme}://{parsed.netloc}"
            probes = [_probe_feed(client, root + p) for p in _FEED_PROBE_PATHS]
            for hit in await asyncio.gather(*probes):
                if hit:
                    result["feeds"].append({
                        "url": hit["url"],
                        "title": "Feed (probed)",
                        "type": hit["content_type"],
                        "source": "path-probe",
                    })
                    break  # one is enough

        # 3. Always offer html_links fallback so the user can grab updates without a feed
        anchor_sample = _sample_links(soup, final_url)
        result["fallback"] = {
            "type": "html_links",
            "url": final_url,
            "anchor_sample": anchor_sample,
            "hint": (
                "No feed detected. The html_links fetcher will track new links under "
                f"{urlparse(final_url).path or '/'} on this page."
                if not result["feeds"]
                else "Feed detected above. html_links is an alternative if the feed is incomplete."
            ),
        }

    return result


def _sample_links(soup: BeautifulSoup, base_url: str, n: int = 5) -> list[dict]:
    """Show the user a preview of links the html_links scraper would emit."""
    parsed = urlparse(base_url)
    src_host = parsed.netloc
    src_base_path = parsed.path.rstrip("/") + "/"
    seen: set[str] = set()
    out: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        abs_url = urljoin(base_url, href)
        p = urlparse(abs_url)
        if p.scheme not in ("http", "https") or p.netloc != src_host:
            continue
        if src_base_path != "/" and not p.path.startswith(src_base_path):
            continue
        clean = p._replace(fragment="").geturl()
        if clean in seen or clean.rstrip("/") == base_url.rstrip("/"):
            continue
        title = a.get_text(strip=True) or a.get("title", "") or a.get("aria-label", "")
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 3:
            continue
        seen.add(clean)
        out.append({"url": clean, "title": title[:120]})
        if len(out) >= n:
            break
    return out


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

    pairs = [(src, s) for s in missing_stories]
    inserted = await save_stories(session, pairs)
    await session.commit()

    return {
        "source_id": source_id,
        "source_name": src.name,
        "available_count": len(available),
        "imported": inserted,
    }
