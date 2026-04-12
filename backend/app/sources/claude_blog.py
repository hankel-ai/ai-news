"""Claude Blog source - scrapes https://claude.com/blog"""
import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .base import Story

logger = logging.getLogger(__name__)

CLAUDE_BLOG_URL = "https://claude.com/blog"


async def fetch_claude_blog(config: dict) -> list[Story]:
    max_stories = config.get("max_stories", 3)
    source_name = config.get("_source_name", "Claude Blog")

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(CLAUDE_BLOG_URL, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch Claude blog: {e}")
            return []

    soup = BeautifulSoup(resp.text, "html.parser")
    stories: list[Story] = []
    seen_urls: set[str] = set()

    article_cards = (
        soup.select("article")
        or soup.select(".blog-post")
        or soup.select("[class*='blog']")
        or soup.select("[class*='post']")
        or soup.select("a[href*='/blog/']")
        or soup.select("main a")
        or soup.select("a")
    )

    for element in article_cards[: max_stories * 3]:
        if len(stories) >= max_stories:
            break

        link_el = element if element.name == "a" else element.find("a")
        if not link_el:
            continue

        href = link_el.get("href", "")
        if not href:
            continue

        if href.startswith("/"):
            href = f"https://claude.com{href}"
        elif not href.startswith("http"):
            href = f"https://claude.com/{href}"

        if "/blog/" not in href or href in seen_urls:
            continue

        title_el = element.find(["h1", "h2", "h3", "h4", "h5"]) or link_el
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 5:
            title = link_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

        summary = ""
        p = element.find("p")
        if p:
            summary = p.get_text(strip=True)[:300]

        stories.append(
            Story(
                title=title,
                url=href,
                source_name=source_name,
                summary=summary,
                published=datetime.now(timezone.utc),
            )
        )
        seen_urls.add(href)

    return stories
