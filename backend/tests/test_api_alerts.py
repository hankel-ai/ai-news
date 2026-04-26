import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Trend
from app.api.alerts import _get_pending_alerts, ack_alert


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future_iso(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past_iso(hours=24):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


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


@pytest.mark.asyncio
async def test_pending_alerts_returns_active_only(db_session):
    # Active: not notified, not expired
    active = Trend(
        topic="llm-release", severity="breaking", story_count=5,
        detected_at=_now_iso(), expires_at=_future_iso(), notified=0,
    )
    # Already notified
    notified = Trend(
        topic="funding", severity="trending", story_count=3,
        detected_at=_now_iso(), expires_at=_future_iso(), notified=1,
    )
    # Expired
    expired = Trend(
        topic="regulation", severity="trending", story_count=2,
        detected_at=_past_iso(48), expires_at=_past_iso(24), notified=0,
    )
    db_session.add_all([active, notified, expired])
    await db_session.flush()

    alerts = await _get_pending_alerts(db_session)

    assert len(alerts) == 1
    assert alerts[0]["topic"] == "llm-release"
    assert alerts[0]["severity"] == "breaking"
    assert alerts[0]["story_count"] == 5


@pytest.mark.asyncio
async def test_pending_alerts_empty_when_none(db_session):
    alerts = await _get_pending_alerts(db_session)
    assert alerts == []


@pytest.mark.asyncio
async def test_ack_alert_marks_notified(db_session):
    trend = Trend(
        topic="test-topic", severity="trending", story_count=2,
        detected_at=_now_iso(), expires_at=_future_iso(), notified=0,
    )
    db_session.add(trend)
    await db_session.flush()
    trend_id = trend.id

    result = await ack_alert(trend_id, session=db_session)

    assert result["id"] == trend_id
    assert result["notified"] is True

    # Verify it's no longer in pending
    pending = await _get_pending_alerts(db_session)
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_ack_nonexistent_alert_raises_404(db_session):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await ack_alert(9999, session=db_session)
    assert exc_info.value.status_code == 404
