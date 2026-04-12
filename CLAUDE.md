# ai-news

## Purpose
Self-hosted web site that aggregates AI news headlines from multiple sources on a configurable schedule. Keeps persistent history in SQLite so the site can be visited any time. Settings tab lets you reconfigure sources, schedule frequency, and display options at runtime without redeploying. Designed to be embeddable inline into the `hankel.ai` Hugo portfolio via an iframe shortcode.

Originated as a pivot from `../ai-podcast` — the source-fetching pipeline is reused, the TTS/podcast/Telegram delivery machinery is dropped.

## Tech Stack
- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2 async, aiosqlite, APScheduler (AsyncIOScheduler), httpx, feedparser, beautifulsoup4, trafilatura
- **Frontend**: React 18 + TypeScript + Vite, TanStack Query, TailwindCSS
- **Storage**: SQLite (WAL mode) on a Longhorn RWO PVC at `/data/ainews.db`
- **Container**: Multi-stage Docker build (node:20-alpine build → python:3.11-slim runtime)
- **Deployment**: Helm chart → K3s, nginx ingress, cert-manager with `letsencrypt-hankel` ClusterIssuer at `news.hankel.ai`
- **CI/CD**: GitHub Actions (`ubuntu-latest` build → `arc-runner-set` deploy), image at `ghcr.io/hankel-ai/ai-news`

## Architecture
- **Single-replica constraint**: APScheduler + SQLite file lock require exactly 1 pod. Deployment strategy is `Recreate` (not RollingUpdate) to prevent double-scheduling during upgrades.
- **Scheduler lives in the FastAPI process** (via lifespan). Settings tab writes `fetch_interval_minutes` to DB; `PUT /api/settings` calls `scheduler.reschedule_from_db()` so interval changes take effect without a pod restart.
- **No authentication**: all endpoints, including Settings writes, are fully public. Accepted trade-off for simplicity. If abuse appears, swap in an API token or split Settings onto a LAN-only ingress.
- **Embedding**: `GET /embed` serves a minimal SSR HTML view styled with the hankel.ai dark palette. CSP `frame-ancestors 'self' https://hankel.ai https://*.hankel.ai` allows iframing from the portfolio. `postMessage` from inside the embed auto-resizes the parent iframe.
- **Dedup**: in-memory `deduplicate()` on each batch (URL + title similarity) → `INSERT OR IGNORE` on `UNIQUE(url_normalized)` catches cross-run dupes.
- **Retention**: nightly `DELETE FROM stories WHERE first_seen_at < datetime('now', -retention_days || ' days')`.

## Folder Structure
```
backend/app/
  main.py              FastAPI app + lifespan + static mount
  config.py            env-only: DB_PATH, DATA_DIR, SEED_PATH, EMBED_ALLOWED_ORIGINS
  security.py          CSP frame-ancestors middleware
  scheduler.py         init_scheduler, reschedule_from_db, run_fetch_job
  db/                  engine, models, migrations, migrations_sql/001_init.sql
  api/                 stories, sources, settings, fetch, health, embed
  pipeline/            aggregator (DB-driven run_once), persist, health_writer
  sources/             copied from ai-podcast (hackernews, rss_generic, reddit, techmeme, implicator, claude_blog, base)
  utils/               dedup, content_scraper, logging_setup
  static/              built frontend assets (vite build output)
frontend/src/
  pages/HeadlinesPage.tsx, SettingsPage.tsx
  components/          StoryCard, StoryList, FiltersBar, SourcesTable, SettingsForm, ...
  lib/api.ts, queryClient.ts
docker/Dockerfile      multi-stage build
helm/ai-news/          Chart.yaml, values.yaml, templates/
.github/workflows/build-and-deploy.yml
```

## Key Commands
```bash
# Backend dev
uvicorn app.main:app --reload --app-dir backend

# Frontend dev (proxies /api to :8000)
cd frontend && npm run dev

# Frontend prod build (writes into backend/app/static)
cd frontend && npm run build

# Tests
pytest backend/tests

# Helm
helm lint ./helm/ai-news
helm template test ./helm/ai-news
helm upgrade --install ai-news ./helm/ai-news -n ai-news --create-namespace
```

## Known Gotchas
- **Single replica**: never set `replicas > 1` or switch to `RollingUpdate`. SQLite file lock + APScheduler cannot handle two pods.
- **Let's Encrypt rate limits**: during initial iteration, set `ingress.enabled=false` and use `kubectl port-forward` instead of hitting the real `letsencrypt-hankel` ClusterIssuer repeatedly.
- **HTML scrapers break silently**: techmeme + implicator are brittle. Check the `source_health` table / Settings diagnostics regularly.
- **Content scraper thread pool**: `utils/content_scraper.py` was rewritten from ai-podcast to use `asyncio.to_thread` instead of a module-level `ThreadPoolExecutor` (which leaks in long-lived servers).

## Related Projects
- `../ai-podcast` — original source; kept unchanged as the podcast version
- `../pihole-helm` — Helm chart conventions used here (`_helpers.tpl`, `Recreate` strategy, lean values, nginx ingress + cert-manager)
- `../container-image-compare` — CI/CD pattern used here (`ubuntu-latest` → `arc-runner-set`, `docker/build-push-action@v7`)
- `../hankel-ai.github.io` — portfolio that embeds `/embed` via a Hugo shortcode
- `../cert-issuer-hankel` — defines the `letsencrypt-hankel` ClusterIssuer
