"""Generic HTML anchor scraper for pages that lack an RSS feed.

Given a page URL, fetch it and emit one Story per matching `<a href>`. By default,
restricts to links whose path is under the source URL's path (so a "what's new"
index yields its sub-pages, not the global nav). Optional regex narrows further.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.utils.content_scraper import enrich_stories

from .base import Story

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def fetch_html_links(config: dict) -> list[Story]:
    url = config["url"]
    max_stories = config.get("max_stories", 10)
    source_name = config.get("_source_name", url)
    link_pattern = config.get("link_pattern")  # optional regex (matches full href)
    link_selector = config.get("link_selector")  # optional CSS scoping selector
    same_domain = config.get("same_domain_only", True)
    require_base_path = config.get("require_base_path", True)

    pattern_re = re.compile(link_pattern) if link_pattern else None

    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA}) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    if link_selector:
        scope = soup.select(link_selector)
        anchors = [a for el in scope for a in (el.find_all("a", href=True) if el.name != "a" else [el])]
    else:
        anchors = soup.find_all("a", href=True)

    parsed_src = urlparse(str(resp.url))
    src_host = parsed_src.netloc
    src_base_path = parsed_src.path.rstrip("/") + "/"

    seen: set[str] = set()
    stories: list[Story] = []

    for a in anchors:
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        abs_url = urljoin(str(resp.url), href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue

        clean = parsed._replace(fragment="").geturl()
        if clean in seen or clean.rstrip("/") == str(resp.url).rstrip("/"):
            continue

        if same_domain and parsed.netloc != src_host:
            continue
        if require_base_path and src_base_path != "/" and not parsed.path.startswith(src_base_path):
            continue
        if pattern_re and not pattern_re.search(abs_url):
            continue

        title = (
            a.get_text(strip=True)
            or a.get("title", "").strip()
            or a.get("aria-label", "").strip()
        )
        if not title or len(title) < 3:
            continue
        title = re.sub(r"\s+", " ", title)[:200]

        seen.add(clean)
        stories.append(Story(title=title, url=clean, source_name=source_name))

        if len(stories) >= max_stories:
            break

    # Titles alone are usually too thin for AI analysis ("Week 19 · May 4–8" tells
    # the LLM nothing). Always pull each linked page's body so analyzer has signal.
    if stories:
        await enrich_stories(stories)

    return stories
