import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Story, Source


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest_asyncio.fixture
async def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _seed_source(session: AsyncSession) -> Source:
    source = Source(
        key="test", name="TestSource", type="rss", url="http://test.com",
        enabled=1, created_at=_now_iso(), updated_at=_now_iso(),
    )
    session.add(source)
    await session.flush()
    return source


async def _seed_stories(session: AsyncSession, source: Source) -> list[Story]:
    stories = []
    for i, (title, score, topics, viewed) in enumerate([
        ("AI Model Released", 95, '["llm-release"]', None),
        ("Funding Round", 70, '["funding"]', "2025-01-01T00:00:00Z"),
        ("Tutorial Post", 40, '["tutorial"]', None),
        ("Low Score Item", 20, '["infrastructure"]', None),
        ("No Score Yet", None, None, None),
    ]):
        s = Story(
            source_id=source.id, title=title,
            url=f"http://test.com/{i}", url_normalized=f"test.com/{i}",
            source_name=source.name, summary=f"Summary {i}",
            first_seen_at=f"2025-01-{10+i:02d}T00:00:00Z",
            relevance_score=score, topics=topics, viewed_at=viewed,
            ai_summary=f"AI summary for {title}" if score else None,
            analyzed_at=_now_iso() if score else None,
        )
        session.add(s)
        stories.append(s)
    await session.flush()
    return stories


@pytest.mark.asyncio
async def test_sort_by_relevance(db_session):
    from app.api.stories import list_stories

    source = await _seed_source(db_session)
    await _seed_stories(db_session, source)

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="relevance", min_score=None, topics=None,
        unread_only=False, session=db_session,
    )

    items = result["items"]
    scores = [it["relevance_score"] for it in items]
    # Non-null scores should come first, in descending order
    non_null = [s for s in scores if s is not None]
    assert non_null == sorted(non_null, reverse=True)
    # Null scores should be at the end
    assert scores[-1] is None


@pytest.mark.asyncio
async def test_sort_by_newest(db_session):
    from app.api.stories import list_stories

    source = await _seed_source(db_session)
    await _seed_stories(db_session, source)

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="newest", min_score=None, topics=None,
        unread_only=False, session=db_session,
    )

    dates = [it["first_seen_at"] for it in result["items"]]
    assert dates == sorted(dates, reverse=True)


async def _seed_backfilled_story(session: AsyncSession, source: Source) -> Story:
    """A May article that only reached the DB today — the resurrection case."""
    s = Story(
        source_id=source.id, title="Week 22 - May 25-29",
        url="http://test.com/w22", url_normalized="test.com/w22",
        source_name=source.name,
        published_at="2026-05-25T00:00:00Z",
        first_seen_at="2026-07-29T02:54:00Z",
    )
    session.add(s)
    await session.flush()
    return s


@pytest.mark.asyncio
async def test_newest_sorts_by_publication_not_ingestion(db_session):
    source = await _seed_source(db_session)
    await _seed_backfilled_story(db_session, source)
    recent = Story(
        source_id=source.id, title="Today's news",
        url="http://test.com/today", url_normalized="test.com/today",
        source_name=source.name,
        published_at="2026-07-28T12:00:00Z",
        first_seen_at="2026-07-28T12:05:00Z",
    )
    db_session.add(recent)
    await db_session.flush()

    from app.api.stories import list_stories

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="newest", min_score=None, topics=None,
        unread_only=False, session=db_session,
    )

    # The May article was ingested last but must not outrank today's news.
    assert [it["title"] for it in result["items"]] == ["Today's news", "Week 22 - May 25-29"]


@pytest.mark.asyncio
async def test_display_date_prefers_published_at(db_session):
    source = await _seed_source(db_session)
    await _seed_backfilled_story(db_session, source)

    from app.api.stories import list_stories

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="newest", min_score=None, topics=None,
        unread_only=False, session=db_session,
    )

    item = result["items"][0]
    assert item["display_date"] == "2026-05-25T00:00:00Z"


@pytest.mark.asyncio
async def test_display_date_falls_back_to_first_seen(db_session):
    source = await _seed_source(db_session)
    await _seed_stories(db_session, source)  # none carry published_at

    from app.api.stories import list_stories

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="newest", min_score=None, topics=None,
        unread_only=False, session=db_session,
    )

    for item in result["items"]:
        assert item["display_date"] == item["first_seen_at"]


@pytest.mark.asyncio
async def test_min_score_filter(db_session):
    from app.api.stories import list_stories

    source = await _seed_source(db_session)
    await _seed_stories(db_session, source)

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="relevance", min_score=50, topics=None,
        unread_only=False, session=db_session,
    )

    assert result["total"] == 2
    for item in result["items"]:
        assert item["relevance_score"] >= 50


@pytest.mark.asyncio
async def test_topic_filter(db_session):
    from app.api.stories import list_stories

    source = await _seed_source(db_session)
    await _seed_stories(db_session, source)

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="relevance", min_score=None, topics="funding",
        unread_only=False, session=db_session,
    )

    assert result["total"] == 1
    assert result["items"][0]["title"] == "Funding Round"
    assert "funding" in result["items"][0]["topics"]


@pytest.mark.asyncio
async def test_unread_only_filter(db_session):
    from app.api.stories import list_stories

    source = await _seed_source(db_session)
    await _seed_stories(db_session, source)

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="relevance", min_score=None, topics=None,
        unread_only=True, session=db_session,
    )

    # 4 out of 5 have viewed_at=None
    assert result["total"] == 4
    for item in result["items"]:
        assert item["viewed_at"] is None


@pytest.mark.asyncio
async def test_response_includes_ai_fields(db_session):
    from app.api.stories import list_stories

    source = await _seed_source(db_session)
    await _seed_stories(db_session, source)

    result = await list_stories(
        limit=50, offset=0, source_id=None, since=None, until=None,
        q=None, sort_by="relevance", min_score=None, topics=None,
        unread_only=False, session=db_session,
    )

    first = result["items"][0]
    assert "ai_summary" in first
    assert "relevance_score" in first
    assert "topics" in first
    assert "analyzed_at" in first
    # topics should be a list, not a JSON string
    assert isinstance(first["topics"], list)
