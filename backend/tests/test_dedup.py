"""Dedup must not collapse distinct entries that share a boilerplate title."""
from app.sources.base import Story
from app.utils.dedup import deduplicate, normalize_url


def _week(n: int, label: str) -> Story:
    return Story(
        title=f"Week {n} · {label}",
        url=f"https://code.claude.com/docs/en/whats-new/2026-w{n}",
        source_name="Claude Code Updates",
    )


WEEKS = [
    _week(29, "July 13–17"),
    _week(28, "July 6–10"),
    _week(27, "June 29 – July 3"),
    _week(26, "June 22–26"),
    _week(25, "June 15–19"),
    _week(24, "June 8–12"),
    _week(23, "June 1–5"),
    _week(22, "May 25–29"),
    _week(21, "May 18–22"),
    _week(20, "May 11–15"),
]


def test_weekly_digests_are_all_kept():
    """Titles differ only in their numbers, so title similarity ran to 0.84 and
    silently discarded 5 of these 10 on every fetch."""
    kept = deduplicate(WEEKS)
    assert len(kept) == len(WEEKS)
    assert {s.url for s in kept} == {s.url for s in WEEKS}


def test_same_url_still_deduped():
    dupes = [_week(22, "May 25–29"), _week(22, "May 25–29")]
    assert len(deduplicate(dupes)) == 1


def test_reworded_headline_still_deduped():
    """The similarity heuristic must keep working for genuine cross-source dupes."""
    stories = [
        Story(title="Oracle fires 21,000 employees to fund AI spending",
              url="https://a.example/oracle", source_name="A", score=10),
        Story(title="Oracle fires 21,000 employees to fund AI spend",
              url="https://b.example/oracle", source_name="B", score=5),
    ]
    kept = deduplicate(stories)
    assert len(kept) == 1
    assert kept[0].source_name == "A"


def test_digit_free_titles_still_deduped():
    stories = [
        Story(title="Anthropic ships a new coding agent",
              url="https://a.example/x", source_name="A"),
        Story(title="Anthropic ships a new coding agent!",
              url="https://b.example/y", source_name="B"),
    ]
    assert len(deduplicate(stories)) == 1


def test_normalize_url_strips_tracking_params():
    assert normalize_url(
        "https://code.claude.com/docs/en/whats-new/2026-w22?utm_source=news"
    ) == normalize_url("https://code.claude.com/docs/en/whats-new/2026-w22")
