import logging
from datetime import datetime, timezone

import httpx

from .base import Story

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "ai-news/1.0 (AI News Aggregator)"}


async def fetch_reddit(config: dict) -> list[Story]:
    subreddit = config["subreddit"]
    sort = config.get("sort", "hot")
    max_stories = config.get("max_stories", 3)
    min_score = config.get("min_score", 50)

    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit=50"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True)
        resp.raise_for_status()

    data = resp.json()
    stories = []

    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("stickied"):
            continue
        if (post.get("score") or 0) < min_score:
            continue

        title = post.get("title", "").strip()
        if not title:
            continue

        if post.get("is_self"):
            post_url = f"https://reddit.com{post.get('permalink', '')}"
            summary = (post.get("selftext") or "")[:300]
        else:
            post_url = post.get("url", f"https://reddit.com{post.get('permalink', '')}")
            summary = ""

        stories.append(Story(
            title=title,
            url=post_url,
            source_name=f"r/{subreddit}",
            summary=summary,
            score=post.get("score"),
            published=datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc),
        ))

        if len(stories) >= max_stories:
            break

    return stories
