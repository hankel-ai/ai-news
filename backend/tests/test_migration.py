import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrations import run


@pytest.mark.asyncio
async def test_migrations_add_intelligence_columns_and_drop_trends(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    await run(engine)

    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(stories)"))
        columns = {row[1] for row in result.fetchall()}
        assert "ai_summary" in columns
        assert "relevance_score" in columns
        assert "topics" in columns
        assert "analyzed_at" in columns

        result = await conn.execute(text("PRAGMA table_info(trends)"))
        assert result.fetchall() == []

    await engine.dispose()
