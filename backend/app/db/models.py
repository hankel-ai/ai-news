from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    keywords: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array
    max_stories: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    min_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subreddit: Mapped[str | None] = mapped_column(String, nullable=True)
    sort: Mapped[str | None] = mapped_column(String, nullable=True)
    extra_config: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON blob
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now)

    stories: Mapped[list["Story"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (
        UniqueConstraint("url_normalized", name="uq_stories_url_normalized"),
        Index("idx_stories_published_desc", "published_at"),
        Index("idx_stories_first_seen_desc", "first_seen_at"),
        Index("idx_stories_source", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    url_normalized: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    article_content: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String, nullable=True)
    keywords_matched: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False, default=_now)
    viewed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, default=None)
    relevance_score: Mapped[int | None] = mapped_column(Integer, default=None)
    topics: Mapped[str | None] = mapped_column(Text, default=None)
    analyzed_at: Mapped[str | None] = mapped_column(Text, default=None)

    source: Mapped[Source] = relationship(back_populates="stories")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


class FetchRun(Base):
    __tablename__ = "fetch_runs"
    __table_args__ = (Index("idx_fetch_runs_started_desc", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    stories_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stories_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class SourceHealth(Base):
    __tablename__ = "source_health"
    __table_args__ = (
        Index("idx_source_health_source_fetched", "source_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("fetch_runs.id", ondelete="SET NULL"), nullable=True
    )
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)
    ok: Mapped[int] = mapped_column(Integer, nullable=False)
    story_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="normal")
    story_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detected_at: Mapped[str] = mapped_column(Text, nullable=False, default=_now)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    notified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
