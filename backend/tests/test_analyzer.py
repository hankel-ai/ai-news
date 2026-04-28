import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Story, Source
from app.llm.base import LLMProvider
from app.pipeline.analyzer import analyze_stories, SYSTEM_PROMPT


class MockProvider(LLMProvider):
    def __init__(self, response: dict):
        self._response = response

    async def complete(self, prompt: str, system: str = "") -> str:
        return json.dumps(self._response)


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


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.asyncio
async def test_analyze_stories_populates_ai_fields(db_session):
    source = Source(
        key="test", name="Test", type="rss", url="http://test.com",
        enabled=1, created_at=_now_iso(), updated_at=_now_iso(),
    )
    db_session.add(source)
    await db_session.flush()

    story = Story(
        source_id=source.id, title="Claude 4 Released", url="http://test.com/1",
        url_normalized="test.com/1", source_name="Test", summary="Big release",
        first_seen_at=_now_iso(),
    )
    db_session.add(story)
    await db_session.flush()

    mock_response = {
        "stories": [{"id": story.id, "summary": "Anthropic releases Claude 4 with major improvements.", "score": 88, "topics": ["llm-release"]}],
    }
    provider = MockProvider(mock_response)
    await analyze_stories(db_session, [story.id], provider)

    await db_session.refresh(story)
    assert story.ai_summary == "Anthropic releases Claude 4 with major improvements."
    assert story.relevance_score == 88
    assert json.loads(story.topics) == ["llm-release"]
    assert story.analyzed_at is not None


def test_system_prompt_requests_json():
    assert "JSON" in SYSTEM_PROMPT
    assert "summary" in SYSTEM_PROMPT
    assert "score" in SYSTEM_PROMPT
    assert "topics" in SYSTEM_PROMPT
