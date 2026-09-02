import json

import httpx
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Story, Source
from app.llm.base import LLMProvider
from app.pipeline.aggregator import run_once


class OkProvider(LLMProvider):
    """Returns a valid analysis payload for whatever it's given."""
    def __init__(self):
        self.calls = 0

    async def complete(self, prompt: str, system: str = "") -> str:
        self.calls += 1
        # Respond for every story id found in the prompt JSON
        req = json.loads(prompt.split("Analyze these stories:\n\n", 1)[1])
        return json.dumps({"stories": [
            {"id": s["id"], "summary": f"sum {s['id']}", "score": 50, "topics": ["product"]}
            for s in req
        ]})


class DeadProvider(LLMProvider):
    def __init__(self):
        self.calls = 0

    async def complete(self, prompt: str, system: str = "") -> str:
        self.calls += 1
        raise httpx.ConnectError("connection refused")


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


@pytest_asyncio.fixture(autouse=True)
async def stub_rss_fetcher(monkeypatch):
    """Keep run_once hermetic: the rss fetcher isn't the dependency under test."""
    from app.pipeline import aggregator

    async def fake_fetch(cfg):
        return []

    monkeypatch.setitem(aggregator.FETCHERS, "rss", fake_fetch)


@pytest_asyncio.fixture
async def seeded_source(db_session):
    src = Source(
        key="test", name="Test", type="rss", url="http://test.com/feed",
        enabled=1, created_at=_now(), updated_at=_now(),
    )
    db_session.add(src)
    await db_session.flush()
    return src


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_story(session, src, url, title="T"):
    session.add(Story(
        source_id=src.id, title=title, url=url, url_normalized=url,
        source_name=src.name, summary="s", first_seen_at=_now(),
    ))
    return url


@pytest.mark.asyncio
async def test_analysis_failure_records_outage(db_session, seeded_source, monkeypatch):
    # Source fetch succeeds (no real fetcher runs — seeded source has a fake feed URL
    # that returns nothing); only the analysis step fails.
    from app.db.models import Setting
    monkeypatch.setattr("app.pipeline.aggregator.get_provider", lambda **kw: DeadProvider())
    # probe must NOT be called on the first failure — it's only for subsequent runs
    async def unexpected_probe(**kw):
        raise AssertionError("probe should not run before outage is recorded")
    monkeypatch.setattr("app.pipeline.aggregator.probe_llm", unexpected_probe)

    _add_story(db_session, seeded_source, "http://test.com/a")
    await db_session.flush()

    run = await run_once(
        db_session, analysis_enabled=True, llm_provider="ollama", llm_model="m",
    )
    assert run.status == "success"  # fetch itself unaffected
    state = await db_session.get(Setting, "llm_outage_state")
    assert state is not None and "ConnectError" in json.loads(state.value)["reason"]


@pytest.mark.asyncio
async def test_outage_skips_llm_and_probes(db_session, seeded_source, monkeypatch):
    # Arrange: outage already recorded
    from app.pipeline.llm_state import record_outage, STATE_KEY
    await record_outage(db_session, reason="prior failure")
    await db_session.commit()

    _add_story(db_session, seeded_source, "http://test.com/a")
    await db_session.flush()

    # Gate closed: probe fails (transport raises) → no provider constructed
    provider_calls = {"n": 0}
    def boom(**kw):
        provider_calls["n"] += 1
        raise AssertionError("get_provider should not be called while outage active and probe fails")

    async def fake_probe(**kw):
        return False, "ConnectError: still down"

    monkeypatch.setattr("app.pipeline.aggregator.get_provider", boom)
    monkeypatch.setattr("app.pipeline.aggregator.probe_llm", fake_probe)

    run = await run_once(
        db_session, analysis_enabled=True, llm_provider="ollama", llm_model="m",
        llm_base_url="http://localhost:11434",
    )
    assert provider_calls["n"] == 0

    from app.db.models import Setting
    raw = (await db_session.execute(select(Setting).where(Setting.key == STATE_KEY))).scalar_one()
    state = json.loads(raw.value)
    assert state["skipped_runs"] == 1


@pytest.mark.asyncio
async def test_probe_success_recovers_and_drains_backlog(db_session, seeded_source, monkeypatch):
    """Probe ok → outage cleared AND unanalyzed backlog (including pre-outage stories) analyzed."""
    from app.pipeline.llm_state import record_outage

    # Pre-outage story left unanalyzed
    _add_story(db_session, seeded_source, "http://test.com/old1")
    _add_story(db_session, seeded_source, "http://test.com/old2")
    await db_session.flush()
    await record_outage(db_session, reason="prior outage")
    await db_session.commit()

    # New stories arriving during outage
    _add_story(db_session, seeded_source, "http://test.com/new1")
    await db_session.flush()

    provider = OkProvider()
    monkeypatch.setattr("app.pipeline.aggregator.get_provider", lambda **kw: provider)

    async def fake_probe(**kw):
        return True, None  # recovered

    monkeypatch.setattr("app.pipeline.aggregator.probe_llm", fake_probe)

    run = await run_once(
        db_session, analysis_enabled=True, llm_provider="ollama", llm_model="m",
    )
    assert run.status == "success"

    from app.pipeline.llm_state import get_outage_state
    assert await get_outage_state(db_session) is None

    stories = (await db_session.execute(select(Story))).scalars().all()
    assert all(s.analyzed_at is not None for s in stories), "backlog must drain"
    assert provider.calls >= 1


@pytest.mark.asyncio
async def test_no_outage_healthy_path_analyzes_new_only(db_session, seeded_source, monkeypatch):
    _add_story(db_session, seeded_source, "http://test.com/a")
    await db_session.flush()

    provider = OkProvider()
    monkeypatch.setattr("app.pipeline.aggregator.get_provider", lambda **kw: provider)
    probe_calls = {"n": 0}

    async def fake_probe(**kw):
        probe_calls["n"] += 1
        return True, None

    monkeypatch.setattr("app.pipeline.aggregator.probe_llm", fake_probe)

    await run_once(db_session, analysis_enabled=True, llm_provider="ollama", llm_model="m")
    assert provider.calls == 1  # healthy path: analyze new stories, no probe needed


@pytest.mark.asyncio
async def test_analysis_success_clears_stale_outage(db_session, seeded_source, monkeypatch):
    """Recovery path: probe ok clears the outage even before any analysis runs."""
    from app.pipeline.llm_state import record_outage, get_outage_state
    await record_outage(db_session, reason="stale")
    await db_session.commit()

    _add_story(db_session, seeded_source, "http://test.com/a")
    await db_session.flush()

    provider = OkProvider()
    monkeypatch.setattr("app.pipeline.aggregator.get_provider", lambda **kw: provider)

    async def recovered_probe(**kw):
        return True, None

    monkeypatch.setattr("app.pipeline.aggregator.probe_llm", recovered_probe)

    await run_once(db_session, analysis_enabled=True, llm_provider="ollama", llm_model="m")
    assert await get_outage_state(db_session) is None
    assert provider.calls == 1  # gate opened → the backlog got analyzed
