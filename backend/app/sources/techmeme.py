import logging
import re

import httpx
from bs4 import BeautifulSoup

from .base import Story

logger = logging.getLogger(__name__)


async def fetch_techmeme(config: dict) -> list[Story]:
    url = config.get("url", "https://www.techmeme.com/")
    max_stories = config.get("max_stories", 4)
    keywords = [k.lower() for k in config.get("keywords", ["AI", "artificial intelligence"])]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={"User-Agent": "ai-news/1.0"})
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    stories = []

    clusters = soup.select(".clus")
    if not clusters:
        clusters = soup.select("[id^='t_']") or soup.select(".ii")

    for cluster in clusters:
        headline_link = cluster.find("a", class_="ourh") or cluster.find("a")
        if not headline_link:
            continue

        title = headline_link.get_text(strip=True)
        link = headline_link.get("href", "")
        if not title or not link:
            continue

        text_lower = title.lower()
        matched = any(re.search(r'\b' + re.escape(kw) + r'\b', text_lower) for kw in keywords)
        if not matched:
            continue

        summary = ""
        summary_el = cluster.find("div", class_="itc") or cluster.find("cite")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

        stories.append(Story(
            title=title,
            url=link,
            source_name="Techmeme",
            summary=summary,
        ))

        if len(stories) >= max_stories:
            break

    return stories
