"""Best-effort publication date for pages that arrive without a feed date.

`html_links`, techmeme and implicator all produce Stories with `published=None`,
so the UI had nothing to date them by except ingestion time. Two sources of
truth, in this order:

1. A date encoded in the URL path. Unambiguous when present, and the only
   correct answer for Anthropic's Claude Code digests — those pages advertise a
   site-wide build date in their metadata (the Week 22 page claims 2026-07-04),
   which would sort a May digest above a July one.
2. The page's own metadata, via trafilatura.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import trafilatura

logger = logging.getLogger(__name__)

# /2026/07/28/slug and /2026-07-28-slug
_PATH_YMD = re.compile(r"/(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?=[-/]|$)")
# /2026-w22 — ISO week, used by code.claude.com/docs/en/whats-new
_PATH_ISO_WEEK = re.compile(r"/(20\d{2})-[wW](\d{1,2})(?=[-/]|$)")

# A date parsed out of a page is a guess; a wrong one far in the future would
# pin the story to the top of the feed indefinitely. Allow a little slack for
# timezone-ahead publishers, reject the rest.
_MAX_FUTURE = timedelta(days=2)
_MIN_YEAR = 1995


def _sane(dt: datetime) -> datetime | None:
    if dt.year < _MIN_YEAR:
        return None
    if dt > datetime.now(timezone.utc) + _MAX_FUTURE:
        return None
    return dt


def date_from_url(url: str) -> datetime | None:
    """Pull a publication date out of the URL path, if it encodes one."""
    path = urlparse(url).path

    m = _PATH_YMD.search(path)
    if m:
        year, month, day = (int(g) for g in m.groups())
        try:
            return _sane(datetime(year, month, day, tzinfo=timezone.utc))
        except ValueError:
            pass  # e.g. /2026/13/45/ — fall through to the ISO-week form

    m = _PATH_ISO_WEEK.search(path)
    if m:
        try:
            monday = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
        return _sane(datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc))

    return None


def date_from_html(html: str) -> datetime | None:
    """Pull a publication date out of the page's own metadata."""
    try:
        meta = trafilatura.extract_metadata(html)
    except Exception as e:  # trafilatura raises on some malformed documents
        logger.debug("metadata extraction failed: %s", e)
        return None

    raw = getattr(meta, "date", None) if meta else None
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        logger.debug("unparseable metadata date %r", raw)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _sane(dt)


def published_for(url: str, html: str) -> datetime | None:
    return date_from_url(url) or date_from_html(html)
