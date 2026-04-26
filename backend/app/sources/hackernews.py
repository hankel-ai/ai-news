import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .base import Story

logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


async def fetch_hackernews(config: dict) -> list[Story]:
    keywords = [k.lower() for k in config.get("keywords", ["AI"])]
    max_stories = config.get("max_stories", 5)
    min_score = config.get("min_score", 50)
    skip_filters = config.get("skip_keyword_filter", False)

    async with httpx.AsyncClient(timeout=15) as client:
        top_resp = await client.get(f"{HN_API}/topstories.json")
        best_resp = await client.get(f"{HN_API}/beststories.json")
        story_ids = list(dict.fromkeys(top_resp.json()[:200] + best_resp.json()[:100]))

        stories = []
        for i in range(0, len(story_ids), 30):
            batch = story_ids[i:i + 30]
            tasks = [client.get(f"{HN_API}/item/{sid}.json") for sid in batch]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for resp in responses:
                if isinstance(resp, Exception):
                    continue
                item = resp.json()
                if not item or item.get("type") != "story":
                    continue
                if (item.get("score") or 0) < min_score:
                    continue

                title = item.get("title", "")
                url = item.get("url", f"https://news.ycombinator.com/item?id={item['id']}")
                matched = _match_keywords(title, url, keywords)
                if not matched and not skip_filters:
                    continue

                stories.append(Story(
                    title=title,
                    url=url,
                    source_name="Hacker News",
                    summary="",
                    score=item.get("score"),
                    published=datetime.fromtimestamp(item.get("time", 0), tz=timezone.utc),
                    keywords_matched=matched,
                ))

            if len(stories) >= max_stories * 3:
                break
            await asyncio.sleep(0.1)

        stories.sort(key=lambda s: s.score or 0, reverse=True)
        stories = stories[:max_stories]

        summary_tasks = [_fetch_summary(client, s) for s in stories]
        await asyncio.gather(*summary_tasks, return_exceptions=True)

    return stories


def _match_keywords(title: str, url: str, keywords: list[str]) -> list[str]:
    text = (title + " " + url).lower()
    matched = []
    for kw in keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE):
            matched.append(kw)
    return matched


async def _fetch_summary(client: httpx.AsyncClient, story: Story):
    if story.url.startswith("https://news.ycombinator.com"):
        return
    try:
        resp = await client.get(story.url, follow_redirects=True, timeout=10)
        if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
            soup = BeautifulSoup(resp.text, "html.parser")
            for prop in ("og:image", "twitter:image", "twitter:image:src"):
                tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
                if tag and tag.get("content") and tag["content"].strip().startswith("http"):
                    story.image_url = tag["content"].strip()
                    break
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                story.summary = meta["content"].strip()[:300]
                return
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) > 80:
                    story.summary = text[:300]
                    return
    except Exception:
        pass
