import difflib
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.sources.base import Story


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    netloc = re.sub(r"^www\.", "", parsed.netloc.lower())
    params = parse_qs(parsed.query)
    clean_params = {
        k: v for k, v in params.items() if not k.startswith(("utm_", "ref", "source"))
    }
    query = urlencode(clean_params, doseq=True)
    path = parsed.path.rstrip("/")
    return urlunparse(("", netloc, path, "", query, ""))


def deduplicate(stories: list[Story]) -> list[Story]:
    seen_urls: dict[str, Story] = {}
    result: list[Story] = []

    for story in stories:
        norm_url = normalize_url(story.url)

        if norm_url in seen_urls:
            existing = seen_urls[norm_url]
            if (story.score or 0) > (existing.score or 0):
                result.remove(existing)
                result.append(story)
                seen_urls[norm_url] = story
            continue

        is_dup = False
        for existing in result:
            ratio = difflib.SequenceMatcher(
                None, story.title.lower(), existing.title.lower()
            ).ratio()
            if ratio >= 0.75:
                if (story.score or 0) > (existing.score or 0):
                    result.remove(existing)
                    del seen_urls[normalize_url(existing.url)]
                    result.append(story)
                    seen_urls[norm_url] = story
                is_dup = True
                break

        if not is_dup:
            result.append(story)
            seen_urls[norm_url] = story

    return result
