import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrations import run


@pytest.mark.asyncio
async def test_migration_004_adds_intelligence_columns(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    await run(engine)

    async with engine.connect() as conn:
        # Check stories columns
        result = await conn.execute(text("PRAGMA table_info(stories)"))
        columns = {row[1] for row in result.fetchall()}
        assert "ai_summary" in columns
        assert "relevance_score" in columns
        assert "topics" in columns
        assert "analyzed_at" in columns

        # Check trends table exists
        result = await conn.execute(text("PRAGMA table_info(trends)"))
        trend_cols = {row[1] for row in result.fetchall()}
        assert "topic" in trend_cols
        assert "severity" in trend_cols
        assert "story_count" in trend_cols
        assert "expires_at" in trend_cols
        assert "notified" in trend_cols

    await engine.dispose()
