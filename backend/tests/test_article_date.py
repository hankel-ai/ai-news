"""Publication dates for sources that carry no feed date."""
from datetime import datetime, timedelta, timezone

from app.utils.article_date import date_from_html, date_from_url, published_for


def test_iso_week_slug():
    """Anthropic's Claude Code digests encode the ISO week: 2026-w22 == May 25."""
    got = date_from_url("https://code.claude.com/docs/en/whats-new/2026-w22")
    assert got is not None
    assert (got.year, got.month, got.day) == (2026, 5, 25)


def test_iso_week_slug_orders_correctly():
    w22 = date_from_url("https://code.claude.com/docs/en/whats-new/2026-w22")
    w29 = date_from_url("https://code.claude.com/docs/en/whats-new/2026-w29")
    assert w22 < w29


def test_ymd_path():
    got = date_from_url("https://example.com/blog/2026/07/28/some-slug")
    assert (got.year, got.month, got.day) == (2026, 7, 28)


def test_dashed_ymd_path():
    got = date_from_url("https://example.com/posts/2026-07-28-some-slug")
    assert (got.year, got.month, got.day) == (2026, 7, 28)


def test_no_date_in_url():
    assert date_from_url("https://implicator.ai/sam-altman-ai-workweek/") is None


def test_impossible_date_ignored():
    assert date_from_url("https://example.com/2026/13/45/slug") is None
    assert date_from_url("https://example.com/2026-w99/slug") is None


def test_future_date_ignored():
    """A bad date far in the future would pin the story to the top forever."""
    year = datetime.now(timezone.utc).year + 2
    assert date_from_url(f"https://example.com/{year}/01/01/slug") is None


def test_html_metadata_date():
    html = """<html><head>
      <meta property="article:published_time" content="2026-07-28T10:00:00Z">
      <title>Some article</title></head><body><p>%s</p></body></html>""" % ("body text " * 40)
    got = date_from_html(html)
    assert got is not None
    assert (got.year, got.month, got.day) == (2026, 7, 28)


def test_url_beats_html_metadata():
    """The Claude docs pages advertise a site-wide build date in their metadata
    (2026-07-04 on the Week 22 page). The slug is authoritative."""
    html = """<html><head>
      <meta property="article:published_time" content="2026-07-04T00:00:00Z">
      <title>Week 22</title></head><body><p>%s</p></body></html>""" % ("body text " * 40)
    got = published_for("https://code.claude.com/docs/en/whats-new/2026-w22", html)
    assert (got.year, got.month, got.day) == (2026, 5, 25)


def test_falls_back_to_html_when_url_has_no_date():
    html = """<html><head>
      <meta property="article:published_time" content="2026-07-28T10:00:00Z">
      <title>Some article</title></head><body><p>%s</p></body></html>""" % ("body text " * 40)
    got = published_for("https://implicator.ai/sam-altman-ai-workweek/", html)
    assert (got.year, got.month, got.day) == (2026, 7, 28)


def test_returns_none_when_nothing_found():
    assert published_for("https://example.com/some-slug", "<html><body>hi</body></html>") is None


def test_result_is_timezone_aware():
    got = date_from_url("https://example.com/blog/2026/07/28/slug")
    assert got.tzinfo is not None
    assert got < datetime.now(timezone.utc) + timedelta(days=3)
