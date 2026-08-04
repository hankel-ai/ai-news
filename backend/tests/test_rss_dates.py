"""Feed dates must survive a non-UTC container timezone.

The pod runs with TZ=America/New_York (helm values), and feedparser hands back
`published_parsed` as a struct_time already normalised to UTC. `time.mktime()`
reads a struct_time as *local* time, so it shifted every RSS story five hours
into the future and the UI rendered fresh stories with a negative age.
"""
import time
from datetime import datetime, timezone

import pytest

from app.sources.rss_generic import fetch_rss

FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>A story about AI</title>
      <link>https://example.com/a</link>
      <description>body</description>
      <pubDate>Tue, 04 Aug 2026 00:42:45 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

EXPECTED = datetime(2026, 8, 4, 0, 42, 45, tzinfo=timezone.utc)


@pytest.fixture
def tz_new_york(monkeypatch):
    """Run the body under TZ=America/New_York, as the pod does."""
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture
def feed_response(monkeypatch):
    class _Resp:
        text = FEED

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr("app.sources.rss_generic.httpx.AsyncClient", _Client)


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="tzset is POSIX-only")
@pytest.mark.asyncio
async def test_feed_date_is_utc_under_non_utc_tz(tz_new_york, feed_response):
    stories = await fetch_rss({"url": "https://example.com/feed", "max_stories": 1})

    assert stories[0].published == EXPECTED


@pytest.mark.asyncio
async def test_feed_date_is_utc_under_ambient_tz(feed_response):
    """Same assertion without touching TZ, so Windows/CI runs cover it too."""
    stories = await fetch_rss({"url": "https://example.com/feed", "max_stories": 1})

    assert stories[0].published == EXPECTED


@pytest.mark.asyncio
async def test_feed_date_is_not_in_the_future(feed_response):
    """The symptom the user saw: a just-published story dated ahead of now."""
    stories = await fetch_rss({"url": "https://example.com/feed", "max_stories": 1})

    assert stories[0].published <= datetime.now(timezone.utc)
