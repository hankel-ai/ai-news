# ai-news

## Purpose
Self-hosted web site that aggregates AI news headlines from multiple sources on a configurable schedule. Keeps persistent history in SQLite so the site can be visited any time. Settings tab lets you reconfigure sources, schedule frequency, and display options at runtime without redeploying. Designed to be embeddable inline into the `hankel.ai` Hugo portfolio via an iframe shortcode.

Originated as a pivot from `../ai-podcast` — the source-fetching pipeline is reused, the TTS/podcast/Telegram delivery machinery is dropped.

## Tech Stack
- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2 async, aiosqlite, APScheduler (AsyncIOScheduler), httpx, feedparser, beautifulsoup4, trafilatura
- **Frontend**: React 18 + TypeScript + Vite, TanStack Query, TailwindCSS
- **Storage**: SQLite (WAL mode) on a Longhorn RWO PVC at `/data/ainews.db`
- **Container**: Multi-stage Docker build (node:20-alpine build → python:3.11-slim runtime)
- **Deployment**: Helm chart → K3s, Traefik ingress, cert-manager with `letsencrypt-hankel` ClusterIssuer at `news.hankel.ai`
- **CI/CD**: GitHub Actions (`ubuntu-latest` build → `arc-runner-set-ainews` deploy), image at `ghcr.io/hankel-ai/ai-news`

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
  db/                  engine, models, migrations, migrations_sql/{001_init,002_add_image_url,003_add_viewed_at,004_add_intelligence}.sql
  api/                 stories, sources, settings, fetch, health, embed, alerts
  pipeline/            aggregator (DB-driven run_once), persist, health_writer
  sources/             copied from ai-podcast (hackernews, rss_generic, reddit, techmeme, implicator, claude_blog, base)
  utils/               dedup, content_scraper, image_extractor, logging_setup
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
helm upgrade --install ai-news ./helm/ai-news -n ai-news
```

## One-time cluster setup (first deploy of this repo)
The CI deploy runs with a namespace-scoped ServiceAccount, so the namespace and RoleBinding must pre-exist. Per-repo, run once:
```bash
kubectl create namespace ai-news
kubectl create rolebinding runner-deploy -n ai-news \
  --clusterrole=admin \
  --serviceaccount=arc-runners:arc-runner-set-ainews-gha-rs-no-permission
```
After that, every `git push` to main builds + deploys on its own. Don't delete the namespace casually (see Known Gotchas on Let's Encrypt).

## Known Gotchas
- **CI deploy runner is per-repo**: `hankel-ai` is a personal GitHub account, which cannot have account-level self-hosted runners. Each repo needs its own AutoscalingRunnerSet. For this repo: `arc-runner-set-ainews` in the `arc-runners` namespace (installed via the `gha-runner-scale-set` chart, scoped to `https://github.com/hankel-ai/ai-news`). The workflow's `runs-on:` on the deploy job must match that name. Do NOT set `runnerScaleSetName` to reuse a name from another scale set in the same namespace — the chart-managed `*-gha-rs-no-permission` ServiceAccount is keyed by scale-set name and will collide.
- **Runner RBAC is namespace-scoped**: the chart-created runner SA (`arc-runner-set-ainews-gha-rs-no-permission`) gets the built-in `admin` ClusterRole via a RoleBinding in the `ai-news` namespace only — not cluster-admin. Consequence: the workflow cannot use `--create-namespace` (that's a cluster-scoped API call). The namespace is pre-provisioned manually (see One-time cluster setup above).
- **Fine-grained PAT must include this repo**: the `github-pat` Secret in `arc-runners` is a fine-grained PAT. When adding a new repo under `hankel-ai`, edit the PAT at github.com/settings/personal-access-tokens to grant **Actions: Read and write** + **Administration: Read and write** on the new repo. Otherwise the controller gets `403 Resource not accessible by personal access token` on runner registration.
- **Single replica**: never set `replicas > 1` or switch to `RollingUpdate`. SQLite file lock + APScheduler cannot handle two pods.
- **Let's Encrypt rate limits**: during initial iteration, set `ingress.enabled=false` and use `kubectl port-forward` instead of hitting the real `letsencrypt-hankel` ClusterIssuer repeatedly.
- **HTML scrapers break silently**: techmeme + implicator are brittle. Check the `source_health` table / Settings diagnostics regularly.
- **Content scraper thread pool**: `utils/content_scraper.py` was rewritten from ai-podcast to use `asyncio.to_thread` instead of a module-level `ThreadPoolExecutor` (which leaks in long-lived servers).
- **Hover preview disabled on mobile**: `StoryCard.tsx` uses `matchMedia("(hover: hover)")` to detect touch devices and skip hover popup entirely. Desktop users can toggle it off via the `hover_preview_enabled` setting.
- **Viewed/read tracking**: `stories.viewed_at` column tracks when an article was read. `PUT /api/stories/{id}/view` marks it. Cards fade to 60% opacity when viewed.
- **AI analysis pipeline**: `pipeline/analyzer.py` sends unanalyzed stories to an LLM (Ollama/Anthropic/LiteLLM) for scoring, summarization, and topic tagging. Integrated into the fetch pipeline (`aggregator.py`); auto-runs when `analysis_enabled=true`. Manual triggers: `POST /api/analyze` (backfill all unanalyzed, capped at 200), `POST /api/stories/{id}/analyze` (single story, returns timing). Settings control `analysis_enabled`, `llm_provider`, `llm_model`, `llm_base_url`, `llm_api_key`. Helm chart exposes `llm.*` values (`provider`, `model`, `baseUrl`, `apiKeySecretName`, `apiKeySecretKey`) which map to `AI_NEWS_LLM_*` env vars; API key uses `secretKeyRef` when `apiKeySecretName` is non-empty. Trend detection / alerts feature was removed (see migration `005_drop_trends.sql`) — too noisy to be useful.
- **Stories API sort/filter**: `GET /api/stories` supports `sort_by` (relevance|newest|source), `min_score`, `topics` (comma-separated), `unread_only`. Response items include `ai_summary`, `relevance_score`, `topics` (parsed list), `analyzed_at`.
- **Per-source reconciliation**: `POST /api/sources/{id}/reconcile` fetches all available articles from a source (bypassing keyword/score filters via `skip_keyword_filter` config flag) and compares against DB. Accessible from Settings > Sources > Reconcile button.
- **Image extraction pipeline**: `image_extractor.py` checks og:image → twitter:image → ld+json → article/figure tags → generic img tags → Google favicon fallback. Reddit fetcher unescapes HTML entities in preview URLs and extracts images from self-post HTML. Techmeme fetcher extracts inline cluster images.

## Related Projects
- `../ai-podcast` — original source; kept unchanged as the podcast version
- `../pihole-helm` — Helm chart conventions used here (`_helpers.tpl`, `Recreate` strategy, lean values, Traefik ingress + cert-manager)
- `../container-image-compare` — CI/CD pattern used here (`ubuntu-latest` → `arc-runner-set`, `docker/build-push-action@v7`)
- `../hankel-ai.github.io` — portfolio that embeds `/embed` via a Hugo shortcode
- `../cert-issuer-hankel` — defines the `letsencrypt-hankel` ClusterIssuer
