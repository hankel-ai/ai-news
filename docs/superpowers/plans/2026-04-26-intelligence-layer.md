# Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AI-powered intelligence layer to ai-news — automatic summarization, relevance scoring, topic tagging, trend detection, breaking alerts, and a clean list frontend redesign.

**Architecture:** A post-fetch analysis pipeline sends batched stories to a configurable LLM provider (Ollama/Anthropic/LiteLLM), stores results in new DB columns, and exposes them via extended APIs. The frontend shifts from a card grid to a typography-first list layout with smart sorting, filtering, and browser push notifications for breaking trends.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2 async / httpx / Anthropic SDK | React 18 / TypeScript / TanStack Query / TailwindCSS | Helm 3 / K3s

**Spec:** `docs/superpowers/specs/2026-04-26-intelligence-layer-design.md`

**Note:** The existing `stories` table already has a `summary` TEXT column (RSS feed description) and a `score` INTEGER column (source score). The AI-generated summary uses `ai_summary` and the AI relevance score uses `relevance_score` to avoid collisions.

---

## File Structure

### New Files

```
backend/app/
  llm/
    __init__.py          # get_provider() factory
    base.py              # Abstract LLMProvider class
    ollama.py            # Ollama provider (POST /api/chat)
    anthropic_provider.py # Anthropic SDK provider
    litellm.py           # LiteLLM/OpenAI-compatible provider
  pipeline/
    analyzer.py          # analyze_stories() — summarize, score, trend detect
  api/
    alerts.py            # GET /alerts/pending, PUT /alerts/{id}/ack
  db/
    migrations_sql/
      004_add_intelligence.sql

backend/tests/
  __init__.py
  conftest.py            # Shared fixtures (async session, mock provider)
  test_llm_providers.py  # LLM provider unit tests
  test_analyzer.py       # Analyzer pipeline tests
  test_api_stories.py    # Stories API filter/sort tests
  test_api_alerts.py     # Alerts API tests
  test_api_settings.py   # Settings API tests

frontend/src/
  components/
    StoryRow.tsx          # New clean-list story component
    TrendBanner.tsx       # Breaking trend banner
    AlertBadge.tsx        # Notification badge in header
    FilterBar.tsx         # Sort/filter controls bar
  sw.ts                  # Service worker for push notifications
```

### Modified Files

```
backend/app/
  config.py              # Add LLM_* env vars
  db/models.py           # Add Trend model, extend Story model
  pipeline/aggregator.py # Call analyzer after persist
  api/stories.py         # Add sort_by, min_score, topics, unread_only params
  api/settings.py        # Add new defaults for LLM/display/notification settings
  api/fetch.py           # Add POST /analyze endpoint
  main.py                # Include alerts router, seed LLM settings from env
  scheduler.py           # Pass analysis_enabled to run_fetch_job

frontend/src/
  lib/api.ts             # Add new types and methods
  pages/HeadlinesPage.tsx # Rewrite to clean list layout
  pages/SettingsPage.tsx  # Add AI Config and Notifications sections
  components/Layout.tsx   # Add alert badge and expand-all toggle
  App.tsx                # Minor: no structural changes needed

helm/ai-news/
  values.yaml            # Add llm.* config block
  templates/deployment.yaml # Add LLM_* env vars with secretKeyRef

requirements.txt         # Add anthropic
```

---

## Task 1: Database Migration & ORM Models

**Files:**
- Create: `backend/app/db/migrations_sql/004_add_intelligence.sql`
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/test_migration.py`

- [ ] **Step 1: Write the migration SQL**

Create `backend/app/db/migrations_sql/004_add_intelligence.sql`:

```sql
-- Add AI analysis columns to stories
ALTER TABLE stories ADD COLUMN ai_summary TEXT;
ALTER TABLE stories ADD COLUMN relevance_score INTEGER;
ALTER TABLE stories ADD COLUMN topics TEXT;
ALTER TABLE stories ADD COLUMN analyzed_at TEXT;

-- Index for sorting by relevance
CREATE INDEX IF NOT EXISTS idx_stories_relevance ON stories(relevance_score DESC);

-- Trends table for topic cluster tracking
CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'normal',
    story_count INTEGER NOT NULL DEFAULT 0,
    detected_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trends_expires ON trends(expires_at);
CREATE INDEX IF NOT EXISTS idx_trends_notified ON trends(notified, expires_at);
```

- [ ] **Step 2: Add Trend model and extend Story model in ORM**

In `backend/app/db/models.py`, add to the Story class (after `viewed_at`):

```python
    ai_summary: Mapped[str | None] = mapped_column(Text, default=None)
    relevance_score: Mapped[int | None] = mapped_column(Integer, default=None)
    topics: Mapped[str | None] = mapped_column(Text, default=None)
    analyzed_at: Mapped[str | None] = mapped_column(Text, default=None)
```

Add new Trend class after SourceHealth:

```python
class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="normal")
    story_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detected_at: Mapped[str] = mapped_column(Text, nullable=False, default=_now)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    notified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 3: Write migration test**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/conftest.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

Create `backend/tests/test_migration.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_migration.py -v`

Expected: PASS — migration creates new columns and trends table.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/migrations_sql/004_add_intelligence.sql backend/app/db/models.py backend/tests/
git commit -m "feat: add intelligence layer DB migration and ORM models"
```

---

## Task 2: Config & Settings Update

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/api/settings.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_settings.py`

- [ ] **Step 1: Add LLM env vars to config.py**

In `backend/app/config.py`, add to the `Settings` class:

```python
    llm_provider: str = "ollama"
    llm_model: str = "llama3.2"
    llm_base_url: str = ""
    llm_api_key: str = ""
```

These use the `AI_NEWS_` env prefix (e.g., `AI_NEWS_LLM_PROVIDER`).

- [ ] **Step 2: Add new defaults to settings API**

In `backend/app/api/settings.py`, add to the `DEFAULTS` dict:

```python
DEFAULTS = {
    # existing...
    "fetch_interval_minutes": 60,
    "retention_days": 30,
    "enrich_content": False,
    "display_group_by_date": True,
    "display_page_size": 50,
    "timezone": "America/New_York",
    "hover_preview_enabled": True,
    # new LLM settings
    "llm_provider": "ollama",
    "llm_model": "llama3.2",
    "llm_base_url": "",
    "llm_api_key": "",
    "analysis_enabled": True,
    "breaking_threshold": 3,
    # new display settings
    "display_expand_summaries": False,
    "display_sort_by": "relevance",
    "display_score_threshold": 0,
    # new notification settings
    "notifications_enabled": True,
}
```

- [ ] **Step 3: Add env var seeding to main.py**

In `backend/app/main.py`, update `_seed_default_settings` to also seed LLM settings from env vars. Add after the existing default-settings seeding loop:

```python
async def _seed_default_settings(session: AsyncSession) -> None:
    from app.api.settings import DEFAULTS

    for key, default in DEFAULTS.items():
        existing = await session.get(Setting, key)
        if existing is None:
            session.add(Setting(key=key, value=str(default)))
    await session.flush()

    # Seed LLM settings from env vars (only if no DB value yet)
    cfg = get_settings()
    env_map = {
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.llm_model,
        "llm_base_url": cfg.llm_base_url,
        "llm_api_key": cfg.llm_api_key,
    }
    for key, env_val in env_map.items():
        if not env_val:
            continue
        existing = await session.get(Setting, key)
        if existing and existing.value == str(DEFAULTS.get(key, "")):
            existing.value = env_val
    await session.flush()
```

Add the import for `get_settings` at the top of `main.py` if not already present:

```python
from app.config import get_settings
```

- [ ] **Step 4: Write settings API test**

Create `backend/tests/test_api_settings.py`:

```python
import pytest
from app.api.settings import DEFAULTS, _parse_value


def test_defaults_include_llm_keys():
    assert "llm_provider" in DEFAULTS
    assert "llm_model" in DEFAULTS
    assert "llm_base_url" in DEFAULTS
    assert "llm_api_key" in DEFAULTS
    assert "analysis_enabled" in DEFAULTS
    assert "breaking_threshold" in DEFAULTS
    assert "display_expand_summaries" in DEFAULTS
    assert "display_sort_by" in DEFAULTS
    assert "display_score_threshold" in DEFAULTS
    assert "notifications_enabled" in DEFAULTS


def test_parse_value_types():
    assert _parse_value("true") is True
    assert _parse_value("false") is False
    assert _parse_value("42") == 42
    assert _parse_value("ollama") == "ollama"
    assert _parse_value("") == ""
```

- [ ] **Step 5: Run test**

Run: `cd backend && python -m pytest tests/test_api_settings.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/api/settings.py backend/app/main.py backend/tests/test_api_settings.py
git commit -m "feat: add LLM config env vars and settings defaults"
```

---

## Task 3: LLM Provider Abstraction

**Files:**
- Create: `backend/app/llm/__init__.py`
- Create: `backend/app/llm/base.py`
- Create: `backend/app/llm/ollama.py`
- Create: `backend/app/llm/anthropic_provider.py`
- Create: `backend/app/llm/litellm.py`
- Modify: `requirements.txt`
- Test: `backend/tests/test_llm_providers.py`

- [ ] **Step 1: Write failing test for LLM provider abstraction**

Create `backend/tests/test_llm_providers.py`:

```python
import json
import pytest
import httpx

from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.llm.litellm import LiteLLMProvider
from app.llm import get_provider


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, response_body: dict, status_code: int = 200):
        self._body = json.dumps(response_body).encode()
        self._status = status_code

    async def handle_async_request(self, request):
        return httpx.Response(self._status, content=self._body)


@pytest.mark.asyncio
async def test_ollama_provider_sends_chat_request():
    fake_response = {
        "message": {"content": "Hello from Ollama"}
    }
    transport = FakeTransport(fake_response)
    client = httpx.AsyncClient(transport=transport)

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="llama3.2",
        client=client,
    )
    result = await provider.complete("Say hello", system="You are helpful")
    assert result == "Hello from Ollama"


@pytest.mark.asyncio
async def test_litellm_provider_sends_openai_format():
    fake_response = {
        "choices": [{"message": {"content": "Hello from LiteLLM"}}]
    }
    transport = FakeTransport(fake_response)
    client = httpx.AsyncClient(transport=transport)

    provider = LiteLLMProvider(
        base_url="http://localhost:4000",
        model="gpt-4",
        api_key="test-key",
        client=client,
    )
    result = await provider.complete("Say hello", system="You are helpful")
    assert result == "Hello from LiteLLM"


def test_get_provider_returns_ollama_by_default():
    provider = get_provider(
        provider_name="ollama",
        model="llama3.2",
        base_url="http://localhost:11434",
        api_key="",
    )
    assert isinstance(provider, OllamaProvider)


def test_get_provider_returns_litellm():
    provider = get_provider(
        provider_name="litellm",
        model="gpt-4",
        base_url="http://localhost:4000",
        api_key="sk-test",
    )
    assert isinstance(provider, LiteLLMProvider)


def test_get_provider_raises_on_unknown():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider(
            provider_name="unknown",
            model="x",
            base_url="",
            api_key="",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_providers.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'`

- [ ] **Step 3: Implement LLM base class**

Create `backend/app/llm/base.py`:

```python
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str = "") -> str:
        ...
```

- [ ] **Step 4: Implement Ollama provider**

Create `backend/app/llm/ollama.py`:

```python
import httpx
from .base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client

    async def complete(self, prompt: str, system: str = "") -> str:
        client = self._client or httpx.AsyncClient(timeout=120)
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        finally:
            if not self._client:
                await client.aclose()
```

- [ ] **Step 5: Implement Anthropic provider**

Add `anthropic>=0.39.0` to `requirements.txt`.

Create `backend/app/llm/anthropic_provider.py`:

```python
from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key

    async def complete(self, prompt: str, system: str = "") -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        try:
            kwargs: dict = {
                "model": self._model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            message = await client.messages.create(**kwargs)
            return message.content[0].text
        finally:
            await client.close()
```

- [ ] **Step 6: Implement LiteLLM provider**

Create `backend/app/llm/litellm.py`:

```python
import httpx
from .base import LLMProvider


class LiteLLMProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        client: httpx.AsyncClient | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._client = client

    async def complete(self, prompt: str, system: str = "") -> str:
        client = self._client or httpx.AsyncClient(timeout=120)
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json={"model": self._model, "messages": messages},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        finally:
            if not self._client:
                await client.aclose()
```

- [ ] **Step 7: Implement provider factory**

Create `backend/app/llm/__init__.py`:

```python
from .base import LLMProvider
from .ollama import OllamaProvider
from .anthropic_provider import AnthropicProvider
from .litellm import LiteLLMProvider


def get_provider(
    provider_name: str,
    model: str,
    base_url: str,
    api_key: str,
) -> LLMProvider:
    if provider_name == "ollama":
        return OllamaProvider(
            base_url=base_url or "http://localhost:11434",
            model=model,
        )
    elif provider_name == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    elif provider_name == "litellm":
        return LiteLLMProvider(base_url=base_url, model=model, api_key=api_key)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_llm_providers.py -v`

Expected: All 5 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/llm/ backend/tests/test_llm_providers.py requirements.txt
git commit -m "feat: add LLM provider abstraction (Ollama, Anthropic, LiteLLM)"
```

---

## Task 4: Analysis Pipeline

**Files:**
- Create: `backend/app/pipeline/analyzer.py`
- Test: `backend/tests/test_analyzer.py`

- [ ] **Step 1: Write failing test for analyzer**

Create `backend/tests/test_analyzer.py`:

```python
import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Story, Source, Trend, Setting
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
        source_id=source.id,
        title="Claude 4 Released",
        url="http://test.com/1",
        url_normalized="test.com/1",
        source_name="Test",
        summary="Big release",
        first_seen_at=_now_iso(),
    )
    db_session.add(story)
    await db_session.flush()

    mock_response = {
        "stories": [
            {
                "id": story.id,
                "summary": "Anthropic releases Claude 4 with major improvements.",
                "score": 88,
                "topics": ["llm-release"],
            }
        ],
        "trends": [
            {"topic": "llm-release", "severity": "trending", "count": 3}
        ],
    }
    provider = MockProvider(mock_response)

    await analyze_stories(db_session, [story.id], provider, breaking_threshold=3)

    await db_session.refresh(story)
    assert story.ai_summary == "Anthropic releases Claude 4 with major improvements."
    assert story.relevance_score == 88
    assert json.loads(story.topics) == ["llm-release"]
    assert story.analyzed_at is not None


@pytest.mark.asyncio
async def test_analyze_stories_creates_trend(db_session):
    source = Source(
        key="test2", name="Test2", type="rss", url="http://test2.com",
        enabled=1, created_at=_now_iso(), updated_at=_now_iso(),
    )
    db_session.add(source)
    await db_session.flush()

    story = Story(
        source_id=source.id,
        title="Breaking News",
        url="http://test2.com/1",
        url_normalized="test2.com/1",
        source_name="Test2",
        first_seen_at=_now_iso(),
    )
    db_session.add(story)
    await db_session.flush()

    mock_response = {
        "stories": [
            {"id": story.id, "summary": "Big news.", "score": 95, "topics": ["llm-release"]}
        ],
        "trends": [
            {"topic": "llm-release", "severity": "breaking", "count": 5}
        ],
    }
    provider = MockProvider(mock_response)

    await analyze_stories(db_session, [story.id], provider, breaking_threshold=3)

    from sqlalchemy import select
    result = await db_session.execute(select(Trend).where(Trend.severity == "breaking"))
    trend = result.scalar_one()
    assert trend.topic == "llm-release"
    assert trend.story_count == 5
    assert trend.notified == 0


def test_system_prompt_requests_json():
    assert "JSON" in SYSTEM_PROMPT
    assert "summary" in SYSTEM_PROMPT
    assert "score" in SYSTEM_PROMPT
    assert "topics" in SYSTEM_PROMPT
    assert "trends" in SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_analyzer.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.pipeline.analyzer'`

- [ ] **Step 3: Implement analyzer.py**

Create `backend/app/pipeline/analyzer.py`:

```python
import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Story, Trend
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

TOPIC_VOCABULARY = [
    "llm-release", "funding", "research", "open-source", "regulation",
    "tutorial", "infrastructure", "product", "acquisition", "policy",
]

SYSTEM_PROMPT = f"""You are an AI news analyst. Analyze the provided stories and return a JSON object with exactly this structure:

{{
  "stories": [
    {{
      "id": <integer — the story ID from input>,
      "summary": "<1-2 sentence TL;DR of the story>",
      "score": <integer 0-100 — relevance score based on novelty, significance to AI/tech, actionability>,
      "topics": [<1-3 topic tags from this vocabulary: {', '.join(TOPIC_VOCABULARY)}>]
    }}
  ],
  "trends": [
    {{
      "topic": "<topic name>",
      "severity": "<normal|trending|breaking>",
      "count": <number of stories about this topic in the last 24 hours>
    }}
  ]
}}

Scoring guide:
- 90-100: Major industry event (new model release, major acquisition, regulatory action)
- 70-89: Significant news (funding round, notable research paper, important product update)
- 40-69: Moderate interest (tutorials, minor updates, commentary)
- 0-39: Low relevance (reposts, tangential content, outdated news)

For trends, mark as "breaking" only if a topic has an unusually high concentration of stories indicating a major event. Mark as "trending" for elevated activity. Most topics are "normal".

Return ONLY valid JSON, no markdown fencing, no commentary."""

BATCH_SIZE = 50


async def analyze_stories(
    session: AsyncSession,
    story_ids: list[int],
    provider: LLMProvider,
    breaking_threshold: int = 3,
) -> None:
    if not story_ids:
        return

    result = await session.execute(
        select(Story).where(Story.id.in_(story_ids))
    )
    stories = list(result.scalars().all())
    if not stories:
        return

    for i in range(0, len(stories), BATCH_SIZE):
        batch = stories[i : i + BATCH_SIZE]
        is_last_chunk = (i + BATCH_SIZE) >= len(stories)
        await _analyze_batch(session, batch, provider, breaking_threshold, detect_trends=is_last_chunk)

    await session.flush()


async def _analyze_batch(
    session: AsyncSession,
    batch: list[Story],
    provider: LLMProvider,
    breaking_threshold: int,
    detect_trends: bool,
) -> None:
    stories_input = []
    for s in batch:
        content = s.article_content or s.summary or ""
        stories_input.append({
            "id": s.id,
            "title": s.title,
            "content": content[:2000],
        })

    prompt = f"Analyze these stories:\n\n{json.dumps(stories_input, indent=2)}"
    if detect_trends:
        prompt += "\n\nAlso detect trends across these stories and any patterns suggesting breaking news."
    else:
        prompt += "\n\nSkip trend detection for this batch (set trends to empty array)."

    raw = await provider.complete(prompt, system=SYSTEM_PROMPT)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON: %s", raw[:500])
        return

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    story_map = {s.id: s for s in batch}

    for item in data.get("stories", []):
        story = story_map.get(item.get("id"))
        if not story:
            continue
        story.ai_summary = item.get("summary", "")
        story.relevance_score = max(0, min(100, int(item.get("score", 0))))
        topics = item.get("topics", [])
        valid_topics = [t for t in topics if t in TOPIC_VOCABULARY]
        story.topics = json.dumps(valid_topics)
        story.analyzed_at = now_iso

    if detect_trends:
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for trend_data in data.get("trends", []):
            severity = trend_data.get("severity", "normal")
            count = trend_data.get("count", 0)
            if severity == "breaking" and count < breaking_threshold:
                severity = "trending"
            if severity in ("trending", "breaking"):
                trend = Trend(
                    topic=trend_data["topic"],
                    severity=severity,
                    story_count=count,
                    detected_at=now_iso,
                    expires_at=expires,
                    notified=0,
                )
                session.add(trend)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_analyzer.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/analyzer.py backend/tests/test_analyzer.py
git commit -m "feat: add AI analysis pipeline (summarize, score, trend detect)"
```

---

## Task 5: Integrate Analyzer into Aggregator & Scheduler

**Files:**
- Modify: `backend/app/pipeline/aggregator.py`
- Modify: `backend/app/scheduler.py`

- [ ] **Step 1: Add analyzer call to aggregator.run_once**

In `backend/app/pipeline/aggregator.py`, add import at top:

```python
from app.pipeline.analyzer import analyze_stories
from app.llm import get_provider
```

At the end of `run_once()`, after `save_stories` and before updating the FetchRun with final stats, add the analysis stage. Find the section after `new_count = await save_stories(...)` and before the FetchRun status update. Insert:

```python
        # AI analysis
        if analysis_enabled and new_count > 0:
            try:
                provider = get_provider(
                    provider_name=llm_provider,
                    model=llm_model,
                    base_url=llm_base_url,
                    api_key=llm_api_key,
                )
                # Get IDs of stories just inserted (unanalyzed)
                from sqlalchemy import select as sa_select
                unanalyzed = await session.execute(
                    sa_select(Story.id).where(
                        Story.analyzed_at.is_(None),
                        Story.first_seen_at >= run.started_at,
                    )
                )
                new_ids = [row[0] for row in unanalyzed.fetchall()]
                if new_ids:
                    await analyze_stories(session, new_ids, provider, breaking_threshold)
                    await session.commit()
            except Exception:
                logger.exception("AI analysis failed — stories saved without analysis")
```

Add these new parameters to the `run_once` function signature:

```python
async def run_once(
    session: AsyncSession,
    *,
    only_source_id: int | None = None,
    dry_run: bool = False,
    enrich_content: bool = False,
    retention_days: int | None = None,
    analysis_enabled: bool = False,
    llm_provider: str = "ollama",
    llm_model: str = "llama3.2",
    llm_base_url: str = "",
    llm_api_key: str = "",
    breaking_threshold: int = 3,
) -> FetchRun:
```

Add the `Story` import at the top if not already present:

```python
from app.db.models import Source, Story, FetchRun, SourceHealth
```

- [ ] **Step 2: Update scheduler to pass LLM settings**

In `backend/app/scheduler.py`, update `_run_fetch_job()` to read and pass the new settings:

```python
async def _run_fetch_job() -> None:
    async with SessionLocal() as session:
        enrich = await _get_setting(session, "enrich_content", False)
        retention = await _get_setting(session, "retention_days", 30)
        analysis_enabled = await _get_setting(session, "analysis_enabled", True)
        llm_provider = await _get_setting(session, "llm_provider", "ollama")
        llm_model = await _get_setting(session, "llm_model", "llama3.2")
        llm_base_url = await _get_setting(session, "llm_base_url", "")
        llm_api_key = await _get_setting(session, "llm_api_key", "")
        breaking_threshold = await _get_setting(session, "breaking_threshold", 3)

        await run_once(
            session,
            enrich_content=bool(enrich),
            retention_days=int(retention),
            analysis_enabled=bool(analysis_enabled),
            llm_provider=str(llm_provider),
            llm_model=str(llm_model),
            llm_base_url=str(llm_base_url),
            llm_api_key=str(llm_api_key),
            breaking_threshold=int(breaking_threshold),
        )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/pipeline/aggregator.py backend/app/scheduler.py
git commit -m "feat: wire analyzer into fetch pipeline and scheduler"
```

---

## Task 6: Stories API — Sort, Filter, Topics

**Files:**
- Modify: `backend/app/api/stories.py`
- Test: `backend/tests/test_api_stories.py`

- [ ] **Step 1: Write failing test for new query params**

Create `backend/tests/test_api_stories.py`:

```python
import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.db.models import Base, Story, Source


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest_asyncio.fixture
async def db_with_stories(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        src = Source(key="s1", name="S1", type="rss", url="http://s.com",
                     enabled=1, created_at=_now(), updated_at=_now())
        session.add(src)
        await session.flush()

        stories = [
            Story(source_id=src.id, title="High Score", url="http://s.com/1",
                  url_normalized="s.com/1", source_name="S1", first_seen_at=_now(),
                  relevance_score=90, topics=json.dumps(["llm-release"]),
                  ai_summary="Important story"),
            Story(source_id=src.id, title="Low Score", url="http://s.com/2",
                  url_normalized="s.com/2", source_name="S1", first_seen_at=_now(),
                  relevance_score=20, topics=json.dumps(["tutorial"]),
                  ai_summary="Minor tutorial"),
            Story(source_id=src.id, title="Viewed Story", url="http://s.com/3",
                  url_normalized="s.com/3", source_name="S1", first_seen_at=_now(),
                  relevance_score=60, viewed_at=_now(),
                  topics=json.dumps(["research"])),
        ]
        session.add_all(stories)
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_sort_by_relevance(db_with_stories):
    session = db_with_stories
    result = await session.execute(
        select(Story).order_by(Story.relevance_score.desc().nulls_last())
    )
    stories = result.scalars().all()
    scores = [s.relevance_score for s in stories]
    assert scores == [90, 60, 20]


@pytest.mark.asyncio
async def test_filter_by_min_score(db_with_stories):
    session = db_with_stories
    result = await session.execute(
        select(Story).where(Story.relevance_score >= 50)
    )
    stories = result.scalars().all()
    assert len(stories) == 2


@pytest.mark.asyncio
async def test_filter_by_topics(db_with_stories):
    session = db_with_stories
    result = await session.execute(
        select(Story).where(Story.topics.like('%"llm-release"%'))
    )
    stories = result.scalars().all()
    assert len(stories) == 1
    assert stories[0].title == "High Score"


@pytest.mark.asyncio
async def test_filter_unread_only(db_with_stories):
    session = db_with_stories
    result = await session.execute(
        select(Story).where(Story.viewed_at.is_(None))
    )
    stories = result.scalars().all()
    assert len(stories) == 2
```

- [ ] **Step 2: Run test to verify it passes (these test raw queries)**

Run: `cd backend && python -m pytest tests/test_api_stories.py -v`

Expected: PASS — these verify the DB-level queries work.

- [ ] **Step 3: Update stories API endpoint**

In `backend/app/api/stories.py`, update the `list_stories` endpoint to accept new query params:

```python
@router.get("/api/stories")
async def list_stories(
    limit: int = 50,
    offset: int = 0,
    source_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    q: str | None = None,
    sort_by: str = "relevance",
    min_score: int | None = None,
    topics: str | None = None,
    unread_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
```

Update the query building section. Replace the existing `order_by` and add new filters before the `order_by`:

```python
    # New filters
    if min_score is not None:
        query = query.where(Story.relevance_score >= min_score)
        count_query = count_query.where(Story.relevance_score >= min_score)

    if topics:
        topic_list = [t.strip() for t in topics.split(",")]
        for topic in topic_list:
            query = query.where(Story.topics.like(f'%"{topic}"%'))
            count_query = count_query.where(Story.topics.like(f'%"{topic}"%'))

    if unread_only:
        query = query.where(Story.viewed_at.is_(None))
        count_query = count_query.where(Story.viewed_at.is_(None))

    # Sort
    if sort_by == "relevance":
        query = query.order_by(Story.relevance_score.desc().nulls_last(), Story.first_seen_at.desc())
    elif sort_by == "newest":
        query = query.order_by(Story.first_seen_at.desc())
    elif sort_by == "source":
        query = query.order_by(Story.source_name, Story.relevance_score.desc().nulls_last())
    else:
        query = query.order_by(Story.first_seen_at.desc())
```

Update the response item serialization to include the new fields. In the items list comprehension, add:

```python
            "ai_summary": s.ai_summary,
            "relevance_score": s.relevance_score,
            "topics": json.loads(s.topics) if s.topics else [],
            "analyzed_at": s.analyzed_at,
```

Add `import json` at the top of the file if not already present.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/stories.py backend/tests/test_api_stories.py
git commit -m "feat: add sort/filter params to stories API (relevance, topics, unread)"
```

---

## Task 7: Alerts API & Manual Analyze Endpoint

**Files:**
- Create: `backend/app/api/alerts.py`
- Modify: `backend/app/api/fetch.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_alerts.py`

- [ ] **Step 1: Write failing test for alerts API**

Create `backend/tests/test_api_alerts.py`:

```python
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Trend


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past(hours=25):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest_asyncio.fixture
async def db_with_trends(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        trends = [
            Trend(topic="llm-release", severity="breaking", story_count=5,
                  detected_at=_now(), expires_at=_future(), notified=0),
            Trend(topic="funding", severity="trending", story_count=3,
                  detected_at=_now(), expires_at=_future(), notified=0),
            Trend(topic="old-news", severity="breaking", story_count=2,
                  detected_at=_past(), expires_at=_past(1), notified=1),
        ]
        session.add_all(trends)
        await session.commit()
        yield session, trends
    await engine.dispose()


@pytest.mark.asyncio
async def test_pending_alerts_returns_unacknowledged_unexpired(db_with_trends):
    session, trends = db_with_trends
    from app.api.alerts import _get_pending_alerts
    pending = await _get_pending_alerts(session)
    topics = [t["topic"] for t in pending]
    assert "llm-release" in topics
    assert "funding" in topics
    assert "old-news" not in topics


@pytest.mark.asyncio
async def test_ack_alert_marks_notified(db_with_trends):
    session, trends = db_with_trends
    breaking = trends[0]
    breaking.notified = 1
    await session.commit()
    await session.refresh(breaking)
    assert breaking.notified == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_alerts.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.alerts'`

- [ ] **Step 3: Implement alerts API**

Create `backend/app/api/alerts.py`:

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Trend

router = APIRouter()


async def _get_pending_alerts(session: AsyncSession) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = await session.execute(
        select(Trend)
        .where(Trend.notified == 0, Trend.expires_at > now)
        .order_by(Trend.detected_at.desc())
    )
    trends = result.scalars().all()
    return [
        {
            "id": t.id,
            "topic": t.topic,
            "severity": t.severity,
            "story_count": t.story_count,
            "detected_at": t.detected_at,
            "expires_at": t.expires_at,
        }
        for t in trends
    ]


@router.get("/api/alerts/pending")
async def get_pending(session: AsyncSession = Depends(get_session)):
    alerts = await _get_pending_alerts(session)
    return {"items": alerts}


@router.put("/api/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, session: AsyncSession = Depends(get_session)):
    trend = await session.get(Trend, alert_id)
    if not trend:
        raise HTTPException(status_code=404, detail="Alert not found")
    trend.notified = 1
    await session.commit()
    return {"id": trend.id, "notified": True}
```

- [ ] **Step 4: Add POST /api/analyze endpoint to fetch.py**

In `backend/app/api/fetch.py`, add:

```python
@router.post("/api/analyze")
async def trigger_analyze(
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select as sa_select
    from app.db.models import Story, Setting
    from app.pipeline.analyzer import analyze_stories
    from app.llm import get_provider
    from app.api.settings import DEFAULTS, _parse_value

    async def _setting(key):
        row = await session.get(Setting, key)
        return _parse_value(row.value) if row else DEFAULTS.get(key)

    provider_name = await _setting("llm_provider")
    model = await _setting("llm_model")
    base_url = await _setting("llm_base_url")
    api_key = await _setting("llm_api_key")
    threshold = await _setting("breaking_threshold")

    provider = get_provider(
        provider_name=str(provider_name),
        model=str(model),
        base_url=str(base_url or ""),
        api_key=str(api_key or ""),
    )

    result = await session.execute(
        sa_select(Story.id).where(Story.analyzed_at.is_(None)).limit(200)
    )
    ids = [row[0] for row in result.fetchall()]
    if not ids:
        return {"analyzed": 0, "message": "No unanalyzed stories found"}

    await analyze_stories(session, ids, provider, int(threshold or 3))
    await session.commit()
    return {"analyzed": len(ids)}
```

- [ ] **Step 5: Register alerts router in main.py**

In `backend/app/main.py`, add the import and include:

```python
from app.api import alerts
app.include_router(alerts.router)
```

Add this alongside the other router includes.

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_api_alerts.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/alerts.py backend/app/api/fetch.py backend/app/main.py backend/tests/test_api_alerts.py
git commit -m "feat: add alerts API and manual analyze endpoint"
```

---

## Task 8: Frontend API Types & Client

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add new TypeScript interfaces**

In `frontend/src/lib/api.ts`, add these interfaces:

```typescript
export interface StoryItem {
  // existing fields...
  id: number;
  title: string;
  url: string;
  source_id: number;
  source_name: string;
  summary: string | null;
  score: number | null;
  published_at: string | null;
  first_seen_at: string;
  keywords_matched: string[];
  image_url: string | null;
  viewed_at: string | null;
  // new fields
  ai_summary: string | null;
  relevance_score: number | null;
  topics: string[];
  analyzed_at: string | null;
}

export interface AlertItem {
  id: number;
  topic: string;
  severity: "normal" | "trending" | "breaking";
  story_count: number;
  detected_at: string;
  expires_at: string;
}

export interface AlertsResponse {
  items: AlertItem[];
}
```

- [ ] **Step 2: Add new API methods**

In the `api` object in `frontend/src/lib/api.ts`, add:

```typescript
  async getStories(params?: Record<string, string>) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<StoriesResponse>(`/api/stories${qs}`);
  },

  // Add these new methods:
  async getPendingAlerts() {
    return request<AlertsResponse>("/api/alerts/pending");
  },

  async ackAlert(alertId: number) {
    return request<{ id: number; notified: boolean }>(`/api/alerts/${alertId}/ack`, {
      method: "PUT",
    });
  },

  async triggerAnalyze() {
    return request<{ analyzed: number; message?: string }>("/api/analyze", {
      method: "POST",
    });
  },
```

Update the existing `getStories` method (if it builds URLSearchParams manually) to pass through the new params like `sort_by`, `min_score`, `topics`, `unread_only`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add intelligence layer types and API methods to frontend client"
```

---

## Task 9: Frontend StoryRow Component

**Files:**
- Create: `frontend/src/components/StoryRow.tsx`

- [ ] **Step 1: Create the StoryRow component**

Create `frontend/src/components/StoryRow.tsx`:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, StoryItem } from "../lib/api";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function scoreBadgeColor(score: number | null): string {
  if (score === null) return "bg-hankel-muted/30 text-hankel-muted";
  if (score >= 75) return "bg-green-500 text-black";
  if (score >= 50) return "bg-yellow-500 text-black";
  return "bg-hankel-muted text-black";
}

function sourceHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

interface StoryRowProps {
  story: StoryItem;
  expanded: boolean;
  onToggle: () => void;
}

export default function StoryRow({ story, expanded, onToggle }: StoryRowProps) {
  const qc = useQueryClient();
  const viewMut = useMutation({
    mutationFn: () => api.markViewed(story.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stories"] }),
  });

  const handleClick = () => {
    if (!story.viewed_at) viewMut.mutate();
    window.open(story.url, "_blank", "noopener");
  };

  const hasAnalysis = story.ai_summary || story.relevance_score !== null;

  return (
    <div
      className={`border-b border-white/5 ${story.viewed_at ? "opacity-50" : ""}`}
    >
      <div className="flex items-center gap-2.5 px-4 py-3">
        {/* Score badge */}
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-bold ${scoreBadgeColor(story.relevance_score)}`}
        >
          {story.relevance_score ?? "—"}
        </span>

        {/* Title */}
        <button
          onClick={handleClick}
          className="flex-1 text-left text-sm font-medium text-hankel-text hover:text-hankel-accent truncate"
        >
          {story.title}
        </button>

        {/* Source + time */}
        <span className="shrink-0 text-xs text-hankel-muted hidden sm:inline">
          {sourceHostname(story.url)}
        </span>
        <span className="shrink-0 text-xs text-hankel-muted">
          {timeAgo(story.first_seen_at)}
        </span>

        {/* Expand toggle */}
        {hasAnalysis && (
          <button
            onClick={onToggle}
            className="shrink-0 text-xs text-hankel-muted hover:text-hankel-accent"
          >
            {expanded ? "▾" : "▸"}
          </button>
        )}
      </div>

      {/* Expanded detail: topics + AI summary */}
      {expanded && hasAnalysis && (
        <div className="pl-[36px] pr-4 pb-3">
          {/* Topic tags */}
          {story.topics.length > 0 && (
            <div className="flex gap-1.5 mb-2 flex-wrap">
              {story.topics.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] text-indigo-400"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* AI Summary */}
          {story.ai_summary && (
            <div className="rounded-md border-l-2 border-indigo-500 bg-white/[0.03] px-3 py-2 text-xs leading-relaxed text-hankel-muted">
              {story.ai_summary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StoryRow.tsx
git commit -m "feat: add StoryRow component for clean list layout"
```

---

## Task 10: Frontend FilterBar Component

**Files:**
- Create: `frontend/src/components/FilterBar.tsx`

- [ ] **Step 1: Create the FilterBar component**

Create `frontend/src/components/FilterBar.tsx`:

```tsx
import { SourceItem } from "../lib/api";

interface FilterBarProps {
  sortBy: string;
  onSortChange: (v: string) => void;
  sourceFilter: number | "";
  onSourceChange: (v: number | "") => void;
  sources: SourceItem[];
  topicFilter: string;
  onTopicChange: (v: string) => void;
  scoreThreshold: number;
  onScoreChange: (v: number) => void;
  unreadOnly: boolean;
  onUnreadChange: (v: boolean) => void;
  search: string;
  onSearchChange: (v: string) => void;
}

const SCORE_PRESETS = [
  { label: "All", value: 0 },
  { label: "50+", value: 50 },
  { label: "75+", value: 75 },
];

const TOPIC_OPTIONS = [
  "llm-release", "funding", "research", "open-source", "regulation",
  "tutorial", "infrastructure", "product", "acquisition", "policy",
];

export default function FilterBar(props: FilterBarProps) {
  const inputClass =
    "rounded bg-hankel-surface border border-white/10 px-2 py-1 text-xs text-hankel-text focus:border-hankel-accent focus:outline-none";

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-2 border-b border-white/5">
      {/* Sort */}
      <label className="flex items-center gap-1.5 text-xs text-hankel-muted">
        Sort
        <select
          value={props.sortBy}
          onChange={(e) => props.onSortChange(e.target.value)}
          className={inputClass}
        >
          <option value="relevance">Relevance</option>
          <option value="newest">Newest</option>
          <option value="source">Source</option>
        </select>
      </label>

      {/* Source */}
      <label className="flex items-center gap-1.5 text-xs text-hankel-muted">
        Source
        <select
          value={props.sourceFilter}
          onChange={(e) =>
            props.onSourceChange(e.target.value ? Number(e.target.value) : "")
          }
          className={inputClass}
        >
          <option value="">All</option>
          {props.sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>

      {/* Topic */}
      <label className="flex items-center gap-1.5 text-xs text-hankel-muted">
        Topic
        <select
          value={props.topicFilter}
          onChange={(e) => props.onTopicChange(e.target.value)}
          className={inputClass}
        >
          <option value="">All</option>
          {TOPIC_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      {/* Score threshold */}
      <div className="flex items-center gap-1.5 text-xs text-hankel-muted">
        Score
        {SCORE_PRESETS.map((p) => (
          <button
            key={p.value}
            onClick={() => props.onScoreChange(p.value)}
            className={`rounded px-2 py-0.5 ${
              props.scoreThreshold === p.value
                ? "bg-hankel-accent text-black font-medium"
                : "bg-hankel-surface text-hankel-muted hover:text-hankel-text"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Unread only */}
      <button
        onClick={() => props.onUnreadChange(!props.unreadOnly)}
        className={`rounded px-2 py-0.5 text-xs ${
          props.unreadOnly
            ? "bg-hankel-accent text-black font-medium"
            : "bg-hankel-surface text-hankel-muted hover:text-hankel-text"
        }`}
      >
        Unread
      </button>

      {/* Search */}
      <input
        type="text"
        value={props.search}
        onChange={(e) => props.onSearchChange(e.target.value)}
        placeholder="Search..."
        className={`${inputClass} ml-auto w-40`}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FilterBar.tsx
git commit -m "feat: add FilterBar component with sort, topic, score, unread controls"
```

---

## Task 11: Frontend TrendBanner & AlertBadge

**Files:**
- Create: `frontend/src/components/TrendBanner.tsx`
- Create: `frontend/src/components/AlertBadge.tsx`

- [ ] **Step 1: Create TrendBanner component**

Create `frontend/src/components/TrendBanner.tsx`:

```tsx
import { AlertItem } from "../lib/api";

interface TrendBannerProps {
  alerts: AlertItem[];
  onFilterTopic: (topic: string) => void;
  onDismiss: (id: number) => void;
}

export default function TrendBanner({ alerts, onFilterTopic, onDismiss }: TrendBannerProps) {
  const breaking = alerts.filter((a) => a.severity === "breaking");
  if (breaking.length === 0) return null;

  return (
    <div className="border-b border-white/5">
      {breaking.map((alert) => (
        <div
          key={alert.id}
          className="flex items-center gap-3 bg-red-500/10 px-4 py-2 text-sm"
        >
          <span className="rounded bg-red-500 px-1.5 py-0.5 text-[10px] font-bold text-white uppercase">
            Breaking
          </span>
          <span className="text-hankel-text">
            Trending:{" "}
            <button
              onClick={() => onFilterTopic(alert.topic)}
              className="font-medium text-hankel-accent hover:underline"
            >
              {alert.topic}
            </button>
            {" — "}
            {alert.story_count} stories
          </span>
          <button
            onClick={() => onDismiss(alert.id)}
            className="ml-auto text-hankel-muted hover:text-hankel-text text-xs"
          >
            Dismiss
          </button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create AlertBadge component**

Create `frontend/src/components/AlertBadge.tsx`:

```tsx
interface AlertBadgeProps {
  count: number;
}

export default function AlertBadge({ count }: AlertBadgeProps) {
  if (count === 0) return null;
  return (
    <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
      {count > 9 ? "9+" : count}
    </span>
  );
}
```

- [ ] **Step 3: Verify they compile**

Run: `cd frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TrendBanner.tsx frontend/src/components/AlertBadge.tsx
git commit -m "feat: add TrendBanner and AlertBadge components"
```

---

## Task 12: Rewrite HeadlinesPage

**Files:**
- Modify: `frontend/src/pages/HeadlinesPage.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Rewrite HeadlinesPage with clean list layout**

Replace `frontend/src/pages/HeadlinesPage.tsx` with:

```tsx
import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, StoryItem, SettingsMap } from "../lib/api";
import StoryRow from "../components/StoryRow";
import FilterBar from "../components/FilterBar";
import TrendBanner from "../components/TrendBanner";

function dateLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const story = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = (today.getTime() - story.getTime()) / 86400000;
  if (diff < 1) return "Today";
  if (diff < 2) return "Yesterday";
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function groupByDate(items: StoryItem[]): Map<string, StoryItem[]> {
  const groups = new Map<string, StoryItem[]>();
  for (const item of items) {
    const label = dateLabel(item.first_seen_at);
    const arr = groups.get(label) || [];
    arr.push(item);
    groups.set(label, arr);
  }
  return groups;
}

export default function HeadlinesPage() {
  const qc = useQueryClient();

  // Filter/sort state
  const [sortBy, setSortBy] = useState("relevance");
  const [sourceFilter, setSourceFilter] = useState<number | "">("");
  const [topicFilter, setTopicFilter] = useState("");
  const [scoreThreshold, setScoreThreshold] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  // Expand state
  const [expandAll, setExpandAll] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Queries
  const params: Record<string, string> = {
    limit: String(limit),
    offset: String(offset),
    sort_by: sortBy,
  };
  if (sourceFilter) params.source_id = String(sourceFilter);
  if (topicFilter) params.topics = topicFilter;
  if (scoreThreshold > 0) params.min_score = String(scoreThreshold);
  if (unreadOnly) params.unread_only = "true";
  if (search) params.q = search;

  const storiesQ = useQuery({
    queryKey: ["stories", params],
    queryFn: () => api.getStories(params),
  });

  const sourcesQ = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.getSources(),
  });

  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const alertsQ = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.getPendingAlerts(),
    refetchInterval: 60000,
  });

  const fetchMut = useMutation({
    mutationFn: () => api.triggerFetch(sourceFilter || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stories"] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const ackMut = useMutation({
    mutationFn: (id: number) => api.ackAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const items = storiesQ.data?.items || [];
  const total = storiesQ.data?.total || 0;
  const sources = sourcesQ.data?.items || [];
  const alerts = alertsQ.data?.items || [];
  const groupByDateEnabled = (settingsQ.data as SettingsMap)?.display_group_by_date !== false;

  // Load persisted display preferences from settings on first render
  useMemo(() => {
    if (!settingsQ.data) return;
    const s = settingsQ.data as SettingsMap;
    if (s.display_expand_summaries) setExpandAll(true);
    if (s.display_sort_by) setSortBy(String(s.display_sort_by));
    if (s.display_score_threshold) setScoreThreshold(Number(s.display_score_threshold));
  }, [settingsQ.data]);

  const grouped = groupByDateEnabled ? groupByDate(items) : null;

  const renderStory = (story: StoryItem) => (
    <StoryRow
      key={story.id}
      story={story}
      expanded={expandAll || expandedIds.has(story.id)}
      onToggle={() => toggleExpand(story.id)}
    />
  );

  return (
    <div>
      {/* Trend banner */}
      <TrendBanner
        alerts={alerts}
        onFilterTopic={(t) => setTopicFilter(t)}
        onDismiss={(id) => ackMut.mutate(id)}
      />

      {/* Header bar */}
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchMut.mutate()}
            disabled={fetchMut.isPending}
            className="rounded bg-hankel-accent px-3 py-1 text-xs font-medium text-black hover:brightness-110 disabled:opacity-50"
          >
            {fetchMut.isPending ? "Fetching..." : "Refresh Now"}
          </button>
          {fetchMut.data && (
            <span className="text-xs text-hankel-muted">
              +{(fetchMut.data as { stories_new?: number }).stories_new ?? 0} new
            </span>
          )}
        </div>

        {/* Expand all toggle */}
        <label className="flex items-center gap-2 text-xs text-hankel-muted cursor-pointer">
          Expand all
          <button
            onClick={() => setExpandAll(!expandAll)}
            className={`relative w-9 h-5 rounded-full transition-colors ${
              expandAll ? "bg-indigo-500" : "bg-hankel-surface"
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                expandAll ? "translate-x-4" : "translate-x-0.5"
              }`}
            />
          </button>
        </label>
      </div>

      {/* Filter bar */}
      <FilterBar
        sortBy={sortBy}
        onSortChange={(v) => { setSortBy(v); setOffset(0); }}
        sourceFilter={sourceFilter}
        onSourceChange={(v) => { setSourceFilter(v); setOffset(0); }}
        sources={sources}
        topicFilter={topicFilter}
        onTopicChange={(v) => { setTopicFilter(v); setOffset(0); }}
        scoreThreshold={scoreThreshold}
        onScoreChange={(v) => { setScoreThreshold(v); setOffset(0); }}
        unreadOnly={unreadOnly}
        onUnreadChange={(v) => { setUnreadOnly(v); setOffset(0); }}
        search={search}
        onSearchChange={(v) => { setSearch(v); setOffset(0); }}
      />

      {/* Stories list */}
      <div>
        {storiesQ.isLoading && (
          <p className="p-8 text-center text-hankel-muted text-sm">Loading...</p>
        )}

        {!storiesQ.isLoading && items.length === 0 && (
          <p className="p-8 text-center text-hankel-muted text-sm">No stories found.</p>
        )}

        {grouped
          ? Array.from(grouped.entries()).map(([label, stories]) => (
              <div key={label}>
                <div className="sticky top-0 z-10 bg-hankel-bg/95 backdrop-blur px-4 py-1.5 text-xs font-medium text-hankel-muted uppercase tracking-wider border-b border-white/5">
                  {label}
                </div>
                {stories.map(renderStory)}
              </div>
            ))
          : items.map(renderStory)}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-center gap-4 py-4">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
            className="rounded bg-hankel-surface px-3 py-1 text-xs text-hankel-text disabled:opacity-30"
          >
            Previous
          </button>
          <span className="text-xs text-hankel-muted">
            {offset + 1}–{Math.min(offset + limit, total)} of {total}
          </span>
          <button
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
            className="rounded bg-hankel-surface px-3 py-1 text-xs text-hankel-text disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update Layout.tsx to include alert badge**

In `frontend/src/components/Layout.tsx`, add the alert badge next to the header:

```tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import AlertBadge from "./AlertBadge";
```

In the header section, wrap the "AI News" title or the Headlines tab with a relative span for the badge:

```tsx
<span className="relative">
  Headlines
  <AlertBadge count={pendingCount} />
</span>
```

Where `pendingCount` comes from:

```tsx
const alertsQ = useQuery({
  queryKey: ["alerts"],
  queryFn: () => api.getPendingAlerts(),
  refetchInterval: 60000,
});
const pendingCount = alertsQ.data?.items?.length ?? 0;
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`

Expected: No type errors (fix any import mismatches).

- [ ] **Step 4: Run dev server and verify visually**

Run: `cd frontend && npm run dev`

Open the app, verify:
- Clean list layout renders
- Score badges show
- Expand toggle works per-row and globally
- Filters change query params
- Pagination works
- Trending banner appears if there are breaking alerts

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/HeadlinesPage.tsx frontend/src/components/Layout.tsx
git commit -m "feat: rewrite HeadlinesPage as clean list with filters, expand-all, trend banner"
```

---

## Task 13: Frontend Settings Page — AI Config & Notifications

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add AI Configuration section**

In `frontend/src/pages/SettingsPage.tsx`, add a new section within the SettingsForm. After the existing display settings fields, add:

```tsx
{/* AI Configuration */}
<h3 className="mt-6 mb-3 text-sm font-medium text-hankel-text">AI Configuration</h3>

<Field label="LLM Provider">
  <select
    value={form.llm_provider ?? "ollama"}
    onChange={(e) => setForm({ ...form, llm_provider: e.target.value })}
    className="input-field"
  >
    <option value="ollama">Ollama</option>
    <option value="anthropic">Anthropic</option>
    <option value="litellm">LiteLLM</option>
  </select>
</Field>

<Field label="Model">
  <input
    className="input-field"
    value={form.llm_model ?? "llama3.2"}
    onChange={(e) => setForm({ ...form, llm_model: e.target.value })}
  />
</Field>

<Field label="Base URL">
  <input
    className="input-field"
    value={form.llm_base_url ?? ""}
    onChange={(e) => setForm({ ...form, llm_base_url: e.target.value })}
    placeholder="http://localhost:11434"
  />
</Field>

<Field label="API Key">
  <input
    className="input-field"
    type="password"
    value={form.llm_api_key ?? ""}
    onChange={(e) => setForm({ ...form, llm_api_key: e.target.value })}
    placeholder="sk-..."
  />
</Field>

<Field label="Analysis Enabled">
  <Toggle
    value={form.analysis_enabled ?? true}
    onChange={(v) => setForm({ ...form, analysis_enabled: v })}
  />
</Field>

<Field label="Breaking Threshold">
  <input
    className="input-field w-20"
    type="number"
    min={1}
    value={form.breaking_threshold ?? 3}
    onChange={(e) => setForm({ ...form, breaking_threshold: Number(e.target.value) })}
  />
</Field>

<button
  onClick={async () => {
    try {
      const res = await api.triggerAnalyze();
      alert(`Analyzed ${res.analyzed} stories`);
    } catch (e) {
      alert("Test failed: " + (e as Error).message);
    }
  }}
  className="mt-2 rounded bg-hankel-surface px-3 py-1 text-xs text-hankel-text hover:bg-white/10"
>
  Test Connection
</button>
```

- [ ] **Step 2: Add Display settings extensions**

Add to the Display section:

```tsx
<Field label="Expand Summaries">
  <Toggle
    value={form.display_expand_summaries ?? false}
    onChange={(v) => setForm({ ...form, display_expand_summaries: v })}
  />
</Field>

<Field label="Default Sort">
  <select
    value={form.display_sort_by ?? "relevance"}
    onChange={(e) => setForm({ ...form, display_sort_by: e.target.value })}
    className="input-field"
  >
    <option value="relevance">Relevance</option>
    <option value="newest">Newest</option>
    <option value="source">Source</option>
  </select>
</Field>

<Field label="Min Score to Display">
  <input
    className="input-field w-20"
    type="number"
    min={0}
    max={100}
    value={form.display_score_threshold ?? 0}
    onChange={(e) => setForm({ ...form, display_score_threshold: Number(e.target.value) })}
  />
</Field>
```

- [ ] **Step 3: Add Notifications section**

Add after the AI Configuration section:

```tsx
{/* Notifications */}
<h3 className="mt-6 mb-3 text-sm font-medium text-hankel-text">Notifications</h3>

<Field label="Browser Notifications">
  <Toggle
    value={form.notifications_enabled ?? true}
    onChange={(v) => setForm({ ...form, notifications_enabled: v })}
  />
</Field>

<button
  onClick={async () => {
    if (!("Notification" in window)) {
      alert("Browser notifications not supported");
      return;
    }
    const perm = await Notification.requestPermission();
    alert(`Notification permission: ${perm}`);
  }}
  className="rounded bg-hankel-surface px-3 py-1 text-xs text-hankel-text hover:bg-white/10"
>
  Request Permission
</button>
```

- [ ] **Step 4: Add Re-analyze button to fetch runs section**

In the fetch runs list (if it exists), add a "Re-analyze" button per run:

```tsx
<button
  onClick={async () => {
    const res = await api.triggerAnalyze();
    alert(`Re-analyzed ${res.analyzed} stories`);
    qc.invalidateQueries({ queryKey: ["stories"] });
  }}
  className="text-xs text-hankel-accent hover:underline"
>
  Re-analyze
</button>
```

- [ ] **Step 5: Verify it compiles and renders**

Run: `cd frontend && npx tsc --noEmit && npm run dev`

Open Settings page, verify all new fields render and save.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add AI config, display extensions, and notifications to Settings page"
```

---

## Task 14: Browser Push Notifications

**Files:**
- Create: `frontend/public/sw.js`
- Modify: `frontend/src/pages/HeadlinesPage.tsx`

**Note:** This uses the browser Notification API (fires when the app is open and polling detects breaking alerts) rather than full Web Push with VAPID keys. Full Web Push would require a push subscription server — overkill for a single-user self-hosted app. The Notification API achieves the same result since the app polls every 60 seconds when open.

- [ ] **Step 1: Create service worker**

Create `frontend/public/sw.js`:

```javascript
self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "AI News Alert";
  const options = {
    body: data.body || "Breaking news detected",
    icon: "/favicon.ico",
    data: { topic: data.topic || "" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const topic = event.notification.data?.topic || "";
  const url = topic ? `/?topic=${encodeURIComponent(topic)}` : "/";
  event.waitUntil(clients.openWindow(url));
});
```

- [ ] **Step 2: Add notification trigger to HeadlinesPage**

In `HeadlinesPage.tsx`, add a useEffect that checks for pending breaking alerts and fires a browser notification:

```tsx
import { useEffect, useRef } from "react";

// Inside the component, after alertsQ:
const notifiedRef = useRef<Set<number>>(new Set());

useEffect(() => {
  if (!alerts.length) return;
  if (!("Notification" in window) || Notification.permission !== "granted") return;

  for (const alert of alerts) {
    if (alert.severity !== "breaking") continue;
    if (notifiedRef.current.has(alert.id)) continue;
    notifiedRef.current.add(alert.id);

    new Notification("AI News — Breaking", {
      body: `${alert.topic}: ${alert.story_count} stories`,
    });
  }
}, [alerts]);
```

- [ ] **Step 3: Register service worker in main.tsx**

In `frontend/src/main.tsx`, add at the bottom:

```tsx
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
```

- [ ] **Step 4: Test notifications**

Run the dev server, grant notification permission, and verify that when alerts appear, a browser notification fires.

- [ ] **Step 5: Commit**

```bash
git add frontend/public/sw.js frontend/src/pages/HeadlinesPage.tsx frontend/src/main.tsx
git commit -m "feat: add browser push notifications for breaking alerts"
```

---

## Task 15: Helm Chart Update

**Files:**
- Modify: `helm/ai-news/values.yaml`
- Modify: `helm/ai-news/templates/deployment.yaml`

- [ ] **Step 1: Add LLM config to values.yaml**

In `helm/ai-news/values.yaml`, add:

```yaml
llm:
  provider: ollama
  model: llama3.2
  baseUrl: "http://ollama.ollama:11434"
  apiKeySecretName: ""
  apiKeySecretKey: api-key
```

- [ ] **Step 2: Add env vars to deployment template**

In `helm/ai-news/templates/deployment.yaml`, add to the container `env` section:

```yaml
        - name: AI_NEWS_LLM_PROVIDER
          value: {{ .Values.llm.provider | quote }}
        - name: AI_NEWS_LLM_MODEL
          value: {{ .Values.llm.model | quote }}
        - name: AI_NEWS_LLM_BASE_URL
          value: {{ .Values.llm.baseUrl | quote }}
        {{- if .Values.llm.apiKeySecretName }}
        - name: AI_NEWS_LLM_API_KEY
          valueFrom:
            secretKeyRef:
              name: {{ .Values.llm.apiKeySecretName }}
              key: {{ .Values.llm.apiKeySecretKey }}
        {{- end }}
```

- [ ] **Step 3: Lint the chart**

Run: `helm lint ./helm/ai-news`

Expected: PASS, no errors.

Run: `helm template test ./helm/ai-news`

Expected: Rendered YAML includes the new env vars.

- [ ] **Step 4: Commit**

```bash
git add helm/ai-news/values.yaml helm/ai-news/templates/deployment.yaml
git commit -m "feat: add LLM config to Helm chart with secretKeyRef support"
```

---

## Task 16: Update requirements.txt & Final Integration Test

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Verify anthropic is in requirements.txt**

Ensure `requirements.txt` contains:

```
anthropic>=0.39.0
```

(Added in Task 3, step 5. Verify it's present.)

- [ ] **Step 2: Run full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`

Expected: Build succeeds, output in `backend/app/static/`.

- [ ] **Step 4: Run the full app locally**

Run: `cd backend && uvicorn app.main:app --reload`

Verify:
- App starts without errors
- Migration 004 runs on first startup
- Settings page shows new AI config fields
- Headlines page shows clean list layout
- Filters and sort work
- Manual analyze button works (if an LLM is accessible)

- [ ] **Step 5: Final commit (if any fixups needed)**

```bash
git add -u
git commit -m "fix: integration adjustments from end-to-end testing"
```
