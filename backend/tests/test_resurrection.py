"""Regression tests for old stories resurfacing as new.

Background: source index pages (Claude Code "what's new", Techmeme, implicator)
keep linking the same articles for months. Retention pruned `stories` by
first_seen_at, and dedup only looked at rows still present, so every pruned
story was re-inserted with first_seen_at=now exactly retention_days later and
jumped back to the top of the feed.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, SeenUrl, Source, Story as StoryModel
from app.pipeline.persist import backfill_url_dates, prune_old, save_stories
from app.sources.base import Story


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@pytest_asyncio.fixture
async def db_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_source(session: AsyncSession) -> Source:
    src = Source(
        key="claude_code_updates", name="Claude Code Updates", type="html_links",
        url="https://code.claude.com/docs/en/whats-new", enabled=1,
        created_at=_now_iso(), updated_at=_now_iso(),
    )
    session.add(src)
    await session.flush()
    return src


def _week22() -> Story:
    return Story(
        title="Week 22 · May 25–29",
        url="https://code.claude.com/docs/en/whats-new/2026-w22",
        source_name="Claude Code Updates",
    )


@pytest.mark.asyncio
async def test_pruned_story_is_not_reinserted(db_session):
    """The exact reported bug: prune, re-fetch the same link, must not come back."""
    src = await _seed_source(db_session)

    assert await save_stories(db_session, [(src, _week22())]) == 1
    await db_session.commit()

    # Age the row past retention, then prune as the nightly job does.
    row = (await db_session.execute(select(StoryModel))).scalars().one()
    row.first_seen_at = "2026-05-25T00:00:00+00:00"
    await db_session.commit()

    assert await prune_old(db_session, retention_days=14) == 1
    await db_session.commit()
    assert (await db_session.execute(select(StoryModel))).scalars().all() == []

    # The whats-new page still links Week 22, so the next fetch offers it again.
    assert await save_stories(db_session, [(src, _week22())]) == 0
    assert (await db_session.execute(select(StoryModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_prune_keeps_the_seen_url_ledger(db_session):
    src = await _seed_source(db_session)
    await save_stories(db_session, [(src, _week22())])
    await db_session.commit()

    row = (await db_session.execute(select(StoryModel))).scalars().one()
    row.first_seen_at = "2026-05-25T00:00:00+00:00"
    await db_session.commit()

    await prune_old(db_session, retention_days=14)
    await db_session.commit()

    ledger = (await db_session.execute(select(SeenUrl))).scalars().all()
    assert len(ledger) == 1
    assert ledger[0].url_normalized == "//code.claude.com/docs/en/whats-new/2026-w22"


@pytest.mark.asyncio
async def test_genuinely_new_url_still_inserts(db_session):
    """The ledger must not block anything that has never been seen."""
    src = await _seed_source(db_session)
    await save_stories(db_session, [(src, _week22())])
    await db_session.commit()

    fresh = Story(
        title="Week 30 · July 20–24",
        url="https://code.claude.com/docs/en/whats-new/2026-w30",
        source_name="Claude Code Updates",
    )
    assert await save_stories(db_session, [(src, fresh)]) == 1


@pytest.mark.asyncio
async def test_backfill_dates_existing_rows(db_session):
    """Rows stored before date extraction must stop reading as today's news."""
    src = await _seed_source(db_session)
    await save_stories(db_session, [(src, _week22())])
    await db_session.commit()

    row = (await db_session.execute(select(StoryModel))).scalars().one()
    assert row.published_at is None

    assert await backfill_url_dates(db_session) == 1
    row = (await db_session.execute(select(StoryModel))).scalars().one()
    assert row.published_at.startswith("2026-05-25")

    # Idempotent: nothing left to do on the next startup.
    assert await backfill_url_dates(db_session) == 0


@pytest.mark.asyncio
async def test_backfill_leaves_dateless_urls_alone(db_session):
    src = await _seed_source(db_session)
    story = Story(title="Some article", url="https://implicator.ai/some-slug/",
                  source_name="implicator.ai")
    await save_stories(db_session, [(src, story)])
    await db_session.commit()

    assert await backfill_url_dates(db_session) == 0
    row = (await db_session.execute(select(StoryModel))).scalars().one()
    assert row.published_at is None


@pytest.mark.asyncio
async def test_ledger_matches_on_normalized_url(db_session):
    """utm_* junk on the same article must not defeat the ledger."""
    src = await _seed_source(db_session)
    await save_stories(db_session, [(src, _week22())])
    await db_session.commit()

    tracked = Story(
        title="Week 22 · May 25–29",
        url="https://code.claude.com/docs/en/whats-new/2026-w22?utm_source=newsletter",
        source_name="Claude Code Updates",
    )
    assert await save_stories(db_session, [(src, tracked)]) == 0
