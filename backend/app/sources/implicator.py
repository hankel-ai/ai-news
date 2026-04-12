import logging

import httpx
from bs4 import BeautifulSoup

from .base import Story

logger = logging.getLogger(__name__)


async def fetch_implicator(config: dict) -> list[Story]:
    url = config.get("url", "https://implicator.ai")
    max_stories = config.get("max_stories", 4)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={"User-Agent": "ai-news/1.0"}, follow_redirects=True)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    stories = []

    articles = (
        soup.select("article") or
        soup.select(".post") or
        soup.select(".card") or
        soup.select(".story") or
        soup.select("a[href]")
    )

    seen_urls = set()
    for article in articles:
        link_el = article if article.name == "a" else article.find("a")
        if not link_el or not link_el.get("href"):
            continue

        href = link_el["href"]
        if href.startswith("/"):
            href = url.rstrip("/") + href
        if not href.startswith("http"):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)

        title_el = article.find(["h1", "h2", "h3", "h4"])
        title = (title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True))
        if not title or len(title) < 10:
            continue

        summary = ""
        p = article.find("p")
        if p:
            summary = p.get_text(strip=True)[:300]

        stories.append(Story(
            title=title,
            url=href,
            source_name="implicator.ai",
            summary=summary,
        ))

        if len(stories) >= max_stories:
            break

    return stories
