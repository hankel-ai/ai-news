import calendar
import logging
from datetime import datetime, timezone

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
                    # feedparser normalises *_parsed to UTC, so the struct_time
                    # must be read as UTC. time.mktime() would read it as local
                    # time and the pod runs TZ=America/New_York, which shifted
                    # every story five hours into the future.
                    published = datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
                except Exception:
                    pass
                break

        stories.append(Story(
            title=title,
            url=link,
            source_name=source_name,
            summary=summary,
            published=published,
        ))

        if len(stories) >= max_stories:
            break

    return stories
