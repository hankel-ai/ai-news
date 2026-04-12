import logging
from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx
from bs4 import BeautifulSoup

from .base import Story

logger = logging.getLogger(__name__)


async def fetch_rss(config: dict) -> list[Story]:
    url = config["url"]
    max_stories = config.get("max_stories", 3)
    source_name = config.get("_source_name", url)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    stories = []

    for entry in feed.entries[:max_stories * 2]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        raw_summary = entry.get("summary", "") or entry.get("description", "")
        summary = BeautifulSoup(raw_summary, "html.parser").get_text(strip=True)[:300]

        published = None
        for date_field in ("published_parsed", "updated_parsed"):
            parsed = entry.get(date_field)
            if parsed:
                try:
                    published = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
                except Exception:
                    pass
                break

        image_url = None
        for media in entry.get("media_thumbnail", []):
            if media.get("url"):
                image_url = media["url"]
                break
        if not image_url:
            for media in entry.get("media_content", []):
                if media.get("url") and media.get("medium") == "image":
                    image_url = media["url"]
                    break
        if not image_url and entry.get("links"):
            for lnk in entry["links"]:
                if lnk.get("type", "").startswith("image/"):
                    image_url = lnk.get("href")
                    break

        stories.append(Story(
            title=title,
            url=link,
            source_name=source_name,
            summary=summary,
            published=published,
            image_url=image_url,
        ))

        if len(stories) >= max_stories:
            break

    return stories
