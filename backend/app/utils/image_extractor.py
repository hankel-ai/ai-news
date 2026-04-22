"""Extract og:image URLs from HTML pages for story thumbnails."""
import asyncio
import json
import logging

import httpx
from bs4 import BeautifulSoup

from app.sources.base import Story

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ai-news/1.0)"}

_SKIP_IMG_PATTERNS = (
    "pixel", "beacon", "tracking", "1x1", "spacer",
    "favicon", "badge", "button", ".svg",
)


def extract_og_image(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    for prop in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if tag and tag.get("content"):
            url = tag["content"].strip()
            if url.startswith("http"):
                return url

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            img = data.get("image")
            if isinstance(img, str) and img.startswith("http"):
                return img
            if isinstance(img, dict):
                u = img.get("url", "")
                if u.startswith("http"):
                    return u
            if isinstance(img, list) and img:
                first = img[0]
                if isinstance(first, str) and first.startswith("http"):
                    return first
                if isinstance(first, dict):
                    u = first.get("url", "")
                    if u.startswith("http"):
                        return u
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    for img_tag in soup.find_all("img", src=True, limit=20):
        src = img_tag["src"].strip()
        if not src.startswith("http"):
            continue
        try:
            w = img_tag.get("width", "")
            h = img_tag.get("height", "")
            if w and int(w) < 100:
                continue
            if h and int(h) < 100:
                continue
        except ValueError:
            pass
        if any(p in src.lower() for p in _SKIP_IMG_PATTERNS):
            continue
        return src

    return None


async def _fetch_image_url(story: Story, client: httpx.AsyncClient) -> None:
    if story.image_url:
        return
    try:
        resp = await client.get(story.url, follow_redirects=True, timeout=10)
        if resp.status_code == 200 and "text/html" in resp.headers.get(
            "content-type", ""
        ):
            story.image_url = extract_og_image(resp.text)
    except Exception:
        pass


async def fetch_images(stories: list[Story]) -> None:
    """Populate image_url on stories that don't already have one."""
    need = [s for s in stories if not s.image_url]
    if not need:
        return
    async with httpx.AsyncClient(headers=_HEADERS) as client:
        await asyncio.gather(
            *[_fetch_image_url(s, client) for s in need],
            return_exceptions=True,
        )
    found = sum(1 for s in need if s.image_url)
    logger.info("og:image extracted: %d/%d stories", found, len(need))
