import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline.llm_state import (
    clear_outage,
    get_outage_state,
    record_outage,
    record_probe,
)

pytestmark = pytest.mark.asyncio


async def _get_raw(session: AsyncSession, key: str) -> str | None:
    from sqlalchemy import select
    from app.db.models import Setting

    result = await session.execute(select(Setting.value).where(Setting.key == key))
    return result.scalar_one_or_none()


async def test_no_outage_by_default(async_session):
    state = await get_outage_state(async_session)
    assert state is None


async def test_record_outage_persists(async_session):
    await record_outage(async_session, reason="ConnectError: connection refused")
    state = await get_outage_state(async_session)
    assert state is not None
    assert state["outage"] is True
    assert state["reason"] == "ConnectError: connection refused"
    assert state["since"]  # ISO timestamp present
    assert state["skipped_runs"] == 0
    # persisted as a Setting row
    raw = await _get_raw(async_session, "llm_outage_state")
    assert raw is not None and "outage" in raw


async def test_record_outage_rewrites_reason_not_since(async_session):
    await record_outage(async_session, reason="first failure")
    state1 = await get_outage_state(async_session)
    await record_outage(async_session, reason="second failure")
    state2 = await get_outage_state(async_session)
    assert state2["reason"] == "second failure"
    assert state2["since"] == state1["since"]  # since = first failure time
    assert state2["skipped_runs"] == 0


async def test_record_outage_resumes_from_existing_row(async_session):
    """Pod restart: existing row keeps since/skipped_runs, just flips outage back on."""
    await record_outage(async_session, reason="first")
    await clear_outage(async_session)
    state_cleared = await get_outage_state(async_session)
    assert state_cleared is None
    # Simulate a stale row surviving restart via re-record
    await record_outage(async_session, reason="second outage")
    state = await get_outage_state(async_session)
    assert state["outage"] is True
    assert state["reason"] == "second outage"


async def test_clear_outage(async_session):
    await record_outage(async_session, reason="down")
    await clear_outage(async_session)
    assert await get_outage_state(async_session) is None
    raw = await _get_raw(async_session, "llm_outage_state")
    assert raw is None


async def test_record_probe_increments_skipped_runs(async_session):
    await record_outage(async_session, reason="down")
    await record_probe(async_session, ok=False)
    state = await get_outage_state(async_session)
    assert state["last_probe_at"] is not None
    assert state["skipped_runs"] == 1

    await record_probe(async_session, ok=False)
    state = await get_outage_state(async_session)
    assert state["skipped_runs"] == 2


async def test_record_probe_ok_clears_outage(async_session):
    await record_outage(async_session, reason="down")
    await record_probe(async_session, ok=True)
    assert await get_outage_state(async_session) is None


async def test_record_probe_without_outage_is_noop(async_session):
    await record_probe(async_session, ok=False)
    assert await get_outage_state(async_session) is None
