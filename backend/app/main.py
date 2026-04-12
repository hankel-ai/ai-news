"""FastAPI application entry point.

Lifespan wires up: migrations → DB seed → scheduler start → yield → scheduler shutdown.
Serves the React SPA as static files at / with a catch-all fallback to index.html.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api import embed, fetch, health, settings, sources, stories
from app.config import get_settings
from app.db.engine import SessionLocal, engine
from app.db.migrations import run as run_migrations
from app.db.models import Setting, Source
from app.scheduler import init_scheduler, shutdown_scheduler, start_scheduler
from app.security import CSPMiddleware
from app.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


async def _seed_sources(seed_path: Path) -> None:
    """On first run, seed the sources table from the ConfigMap JSON."""
    async with SessionLocal() as session:
        count = (await session.execute(select(Source))).scalars().first()
        if count is not None:
            return

        if not seed_path.exists():
            logger.warning("seed file not found: %s", seed_path)
            return

        raw = seed_path.read_text(encoding="utf-8")
        items = json.loads(raw)
        for item in items:
            session.add(
                Source(
                    key=item["key"],
                    name=item["name"],
                    type=item["type"],
                    url=item.get("url"),
                    enabled=1 if item.get("enabled", True) else 0,
                    keywords=json.dumps(item["keywords"]) if item.get("keywords") else None,
                    max_stories=item.get("max_stories", 5),
                    min_score=item.get("min_score"),
                    subreddit=item.get("subreddit"),
                    sort=item.get("sort"),
                    extra_config=json.dumps(item["extra_config"]) if item.get("extra_config") else None,
                )
            )
        await session.commit()
        logger.info("seeded %d sources from %s", len(items), seed_path)


async def _seed_default_settings() -> None:
    """Populate missing settings keys with defaults."""
    from app.api.settings import DEFAULTS

    async with SessionLocal() as session:
        for key, default_val in DEFAULTS.items():
            existing = await session.get(Setting, key)
            if existing is None:
                session.add(Setting(key=key, value=default_val))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    setup_logging(cfg.log_level)
    logger.info("starting ai-news")

    await run_migrations()
    await _seed_sources(cfg.seed_path)
    await _seed_default_settings()

    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(Setting.value).where(Setting.key == "fetch_interval_minutes")
            )
        ).scalar_one_or_none()
        interval = int(row) if row else 60

    init_scheduler()
    await start_scheduler(interval)

    yield

    shutdown_scheduler()
    await engine.dispose()
    logger.info("ai-news stopped")


app = FastAPI(title="ai-news", lifespan=lifespan)

app.add_middleware(CSPMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stories.router)
app.include_router(sources.router)
app.include_router(settings.router)
app.include_router(fetch.router)
app.include_router(health.router)
app.include_router(embed.router)

_static_dir = get_settings().static_dir
if _static_dir.is_dir() and (_static_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        file = _static_dir / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_static_dir / "index.html")
