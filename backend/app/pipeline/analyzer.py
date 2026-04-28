import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Story
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
  ]
}}

Scoring guide:
- 90-100: Major industry event (new model release, major acquisition, regulatory action)
- 70-89: Significant news (funding round, notable research paper, important product update)
- 40-69: Moderate interest (tutorials, minor updates, commentary)
- 0-39: Low relevance (reposts, tangential content, outdated news)

Return ONLY valid JSON, no markdown fencing, no commentary."""

BATCH_SIZE = 50


async def analyze_stories(
    session: AsyncSession,
    story_ids: list[int],
    provider: LLMProvider,
) -> None:
    if not story_ids:
        return

    result = await session.execute(select(Story).where(Story.id.in_(story_ids)))
    stories = list(result.scalars().all())
    if not stories:
        return

    for i in range(0, len(stories), BATCH_SIZE):
        batch = stories[i : i + BATCH_SIZE]
        await _analyze_batch(session, batch, provider)

    await session.flush()


async def _analyze_batch(
    session: AsyncSession,
    batch: list[Story],
    provider: LLMProvider,
) -> None:
    stories_input = []
    for s in batch:
        content = s.article_content or s.summary or ""
        stories_input.append({"id": s.id, "title": s.title, "content": content[:2000]})

    prompt = f"Analyze these stories:\n\n{json.dumps(stories_input, indent=2)}"
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
