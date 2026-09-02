import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Setting
from app.pipeline.llm_state import record_outage, STATE_KEY


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
async def test_llm_status_reports_outage(db_session):
    from app.api.fetch import llm_status

    await record_outage(db_session, reason="ConnectError: connection refused")
    result = await llm_status(session=db_session)

    assert result["outage"] is True
    assert "ConnectError" in result["reason"]
    assert result["since"]
    assert result["skipped_runs"] == 0


@pytest.mark.asyncio
async def test_llm_status_healthy(db_session):
    from app.api.fetch import llm_status

    result = await llm_status(session=db_session)
    assert result["outage"] is False
    assert result["reason"] is None
    assert "analysis_enabled" in result


@pytest.mark.asyncio
async def test_llm_status_survives_restart_with_outage_false(db_session):
    """A state row with outage=false must not be reported as an outage."""
    from app.api.fetch import llm_status

    db_session.add(Setting(key=STATE_KEY, value=json.dumps({"outage": False})))
    await db_session.flush()
    result = await llm_status(session=db_session)
    assert result["outage"] is False


@pytest.mark.asyncio
async def test_settings_put_rejects_outage_state_key(db_session):
    """The settings endpoint is public — it must not be able to fake/clear the banner."""
    from app.api.settings import update_settings

    with pytest.raises(Exception):
        await update_settings(body={"llm_outage_state": json.dumps({"outage": False})}, session=db_session)

    # The forbidden key must not have been written
    row = await db_session.get(Setting, "llm_outage_state")
    assert row is None
