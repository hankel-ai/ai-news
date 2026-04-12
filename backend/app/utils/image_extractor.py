"""Extract og:image URLs from HTML pages for story thumbnails."""
import asyncio
import logging

import httpx
from bs4 import BeautifulSoup

from app.sources.base import Story

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ai-news/1.0)"}


def extract_og_image(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for prop in ("og:image", "twitter:image", "twitter:image:src"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if tag and tag.get("content"):
            url = tag["content"].strip()
            if url.startswith("http"):
                return url
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
