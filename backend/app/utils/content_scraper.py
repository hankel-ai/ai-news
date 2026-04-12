"""Fetch and extract clean article body text from URLs.

Rewritten from ai-podcast to use asyncio.to_thread instead of a module-level
ThreadPoolExecutor, which would leak thread pool resources in a long-lived
FastAPI process.
"""
import asyncio
import logging

import httpx
import trafilatura

from app.sources.base import Story

logger = logging.getLogger(__name__)

_TIMEOUT = 15
_MAX_CONTENT_CHARS = 3000


def _extract_text(html: str) -> str:
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    return text or ""


async def fetch_article_content(story: Story, client: httpx.AsyncClient) -> None:
    if story.article_content:
        return
    try:
        resp = await client.get(story.url, follow_redirects=True, timeout=_TIMEOUT)
        resp.raise_for_status()
        text = await asyncio.to_thread(_extract_text, resp.text)
        story.article_content = text[:_MAX_CONTENT_CHARS] if text else ""
    except Exception as e:
        logger.debug(f"Content scrape failed for {story.url}: {e}")


async def enrich_stories(stories: list[Story]) -> None:
    if not stories:
        return
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [fetch_article_content(s, client) for s in stories]
        await asyncio.gather(*tasks, return_exceptions=True)
    scraped = sum(1 for s in stories if s.article_content)
    logger.info(f"Article content scraped: {scraped}/{len(stories)} stories")
