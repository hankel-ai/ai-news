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
- **Dedup**: in-memory `deduplicate()` on each batch (URL + title similarity) → `INSERT OR IGNORE` on `UNIQUE(url_normalized)` catches cross-run dupes → the `seen_urls` ledger catches anything already pruned.
- **Retention**: nightly `DELETE FROM stories WHERE first_seen_at < datetime('now', -retention_days || ' days')`. Deliberately does **not** touch `seen_urls`.
- **Story dates**: `published_at` is publication time (may be NULL), `first_seen_at` is ingestion time. Everything user-facing dates and sorts by `coalesce(published_at, first_seen_at)`, exposed to the frontend as `display_date`.

## Folder Structure
```
backend/app/
  main.py              FastAPI app + lifespan + static mount
  config.py            env-only: DB_PATH, DATA_DIR, SEED_PATH, EMBED_ALLOWED_ORIGINS
  security.py          CSP frame-ancestors middleware
  scheduler.py         init_scheduler, reschedule_from_db, run_fetch_job
  db/                  engine, models, migrations, migrations_sql/{001_init,...,006_seen_urls,007_drop_stale_columns}.sql
  api/                 stories, sources, settings, fetch, health, embed, alerts
  pipeline/            aggregator (DB-driven run_once), persist, health_writer
  sources/             copied from ai-podcast (hackernews, rss_generic, reddit, techmeme, implicator, claude_blog, base) + html_links (generic anchor scraper for sites without a feed; filters to same-host + same-base-path, optional link_pattern regex via extra_config; always calls enrich_stories so analyzer has content beyond just titles)
  utils/               dedup, content_scraper, article_date, logging_setup
  static/              built frontend assets (vite build output)
frontend/src/
  pages/HeadlinesPage.tsx, SettingsPage.tsx
  components/          StoryRow, FilterBar, Layout
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
- **Hover preview removed (2026-07-29)**: the hover popup lived in `StoryCard.tsx`, which was never rendered, so the feature had been dead for some time. Deleted along with `StoryCard`: `components/PreviewPopup.tsx`, the `hover_preview_enabled` key in `api/settings.py` `DEFAULTS`, its field in `api.ts` `SettingsMap`, and the Settings toggle. The leftover `hover_preview_enabled` row in `settings` is deleted by migration `007`.
- **Viewed/read tracking**: `stories.viewed_at` column tracks when an article was read. `PUT /api/stories/{id}/view` marks it. Cards fade to 60% opacity when viewed.
- **AI analysis pipeline**: `pipeline/analyzer.py` sends unanalyzed stories to an LLM (Ollama/Anthropic/LiteLLM) for scoring, summarization, and topic tagging. Before each batch, the analyzer auto-enriches any story with empty `article_content`+`summary` via trafilatura (otherwise the LLM gets only a title and either says "No content provided" or silently drops the story). Stories the LLM silently drops are still marked `analyzed_at` (with score=0, empty summary) so they don't get retried on every fetch run forever. Integrated into the fetch pipeline (`aggregator.py`); auto-runs when `analysis_enabled=true`. Manual triggers: `POST /api/analyze` (backfill all unanalyzed, capped at 200), `POST /api/stories/{id}/analyze` (single story, returns timing). Settings control `analysis_enabled`, `llm_provider`, `llm_model`, `llm_base_url`, `llm_api_key`. Helm chart exposes `llm.*` values (`provider`, `model`, `baseUrl`, `apiKeySecretName`, `apiKeySecretKey`) which map to `AI_NEWS_LLM_*` env vars; API key uses `secretKeyRef` when `apiKeySecretName` is non-empty. Trend detection / alerts feature was removed (see migration `005_drop_trends.sql`) — too noisy to be useful.
- **Stories API sort/filter**: `GET /api/stories` supports `sort_by` (relevance|newest|source), `min_score`, `topics` (comma-separated), `unread_only`. Response items include `ai_summary`, `relevance_score`, `topics` (parsed list), `analyzed_at`.
- **Per-source reconciliation**: `POST /api/sources/{id}/reconcile` fetches all available articles from a source (bypassing keyword/score filters via `skip_keyword_filter` config flag) and compares against DB. Accessible from Settings > Sources > Reconcile button.
- **Feed auto-detect + html_links fallback**: `POST /api/sources/detect-feed` probes `<link rel="alternate">` and common feed paths (`/feed`, `/rss`, `/feed.xml`, `/atom.xml`, `/index.xml`); always returns a `fallback` with a 5-link preview using the same heuristic as `html_links` (same host + same base path). Surfaced via the Detect button in the Add Source form. For sites with no feed (e.g. `code.claude.com/docs/en/whats-new`), pick type `html_links` — it tracks new anchors under the same path on each fetch. `link_pattern` (regex) lives in `extra_config` for further filtering.
- **Old stories resurfacing as new (fixed 2026-07-29)**: retention pruned `stories` by `first_seen_at` while source index pages (Claude Code "what's new", Techmeme, implicator) kept linking the same articles for months, so every pruned story was re-inserted with `first_seen_at=now` exactly `retention_days` later and jumped back to the top. Three parts to the fix, don't undo any of them in isolation:
  1. `seen_urls` table (migration `006`) — permanent ledger of every `url_normalized` ever ingested, checked by `save_stories()` and **never pruned**. Grows ~40 rows/day; that's intentional.
  2. `utils/article_date.py` — infers `published_at` for feedless sources. **URL-path dates beat page metadata**: the Claude docs pages advertise a site-wide build date (the Week 22 page claims `2026-07-04`), which would sort a May digest above a July one. `/2026-w22` is parsed as an ISO week → 2026-05-25. Inferred dates more than 2 days in the future are discarded.
  3. `backfill_url_dates()` runs from the lifespan on every startup — idempotent, only scans rows where `published_at IS NULL`.
  4. `apply_url_dates()` runs at the **start** of `enrich_stories()`, before any network call. URL-encoded dates are knowable without the page, and originally the date was only assigned after a successful GET — so when Week 24's fetch failed (`scraped: 9/10`), it landed with `published_at` NULL, dated by ingestion time, and sat at the top of the feed looking exactly like the bug that was just fixed. Never move date assignment back inside the fetch.
- **Negative story ages / RSS dates 5h in the future (fixed 2026-08-03)**: `rss_generic.py` built `published` with `datetime.fromtimestamp(mktime(parsed), tz=utc)`. feedparser normalises `published_parsed` to a **UTC** `struct_time`, but `time.mktime()` reads a `struct_time` as **local** time — and the pod sets `TZ=America/New_York` (`values.yaml: timezone`, wired to the `TZ` env var in `deployment.yaml`). Every RSS story therefore landed exactly +5h in the future (feedparser sets `tm_isdst=0`, so it's the *standard* offset year-round, not +4h in summer), and anything fresher than 5h rendered as a negative age in `StoryRow.timeAgo()`. Fixed with `calendar.timegm(parsed)`, which reads the struct as UTC. `hackernews.py`/`reddit.py` were never affected — they pass real epoch seconds to `fromtimestamp`. Regression tests in `backend/tests/test_rss_dates.py`; note the TZ-realistic one needs `time.tzset()` and so **skips on Windows** — run it on Linux (WSL/CI) to actually exercise it. **CI does not run pytest at all**, so nothing catches this automatically yet.
- **Beware `TZ` when reproducing date bugs on Windows**: setting `$env:TZ="America/New_York"` does *not* work — the MSVC CRT wants `EST5EDT` and silently falls back to **UTC** on an unparseable value, which masks exactly this class of bug. Leave `TZ` unset to get the machine's real local zone.
- **Dedup and serial titles**: `deduplicate()` compares the numbers in two titles before trusting the 0.75 similarity ratio. Without that guard "Week 25 · June 15–19" vs "Week 23 · June 1–5" scores 0.84 and half of every weekly-digest batch was silently discarded (5 of 10, on every fetch for two months). Cross-source dupes of the same story quote the same figures, so they still collapse.
- **Memory / OOM restarts (diagnosed 2026-07-29)**: the pod was OOMKilled every ~5h (20 restarts in 10 days) on the 5th fetch run. Not a Python leak — `tracemalloc` over 4 real pipeline runs holds flat at 29.3MB with the object count *falling*. The memory is C allocations `tracemalloc` cannot see: each run parses ~50 HTML documents through lxml/trafilatura across the ~20 threads `asyncio.to_thread` spawns, glibc hands each thread its own arena (default cap `8 x ncores` = 128 on the 16-thread `mini` node) and never returns them, so RSS ratchets to each run's peak — `VmRSS == VmHWM` exactly, and flat between runs. Fixed with `MALLOC_ARENA_MAX=2` (`values.yaml: mallocArenaMax`). Removing the unused image pipeline (below) cut ~25 of the ~75 page-parses per run. If it recurs, the remaining lever is `enrich_stories()`, which still `asyncio.gather`s over the whole batch with no concurrency limit and no response size cap.
- **Diagnosing an OOM here**: a killed run leaves **no** `fetch_runs` row at all — the whole transaction rolls back, so `status='running'` rows never appear. Look for *missing* hours in `select started_at from fetch_runs order by id desc` instead; the gap timestamp is the kill time.
- **Migration files must not contain a semicolon inside a comment**: `migrations.py` splits each file on `;` and runs the fragments individually (aiosqlite executes one statement at a time), so a semicolon in a `--` comment splits mid-comment and the remainder is fed to SQLite as a statement. Cost me two failed attempts on `007`. Always dry-run a new migration against a copy of the prod DB before shipping.
- **Stale columns dropped (migration `007`, 2026-07-29)**: `stories.image_url` (dead with the image pipeline) and `fetch_runs.error` (declared in `001_init`, never once written — 0 of 2193 rows — and run-level failure is already covered by `fetch_runs.status` plus `source_health`). Also deletes three orphaned `settings` rows: `hover_preview_enabled`, and `breaking_threshold` + `notifications_enabled` left over from the trends/alerts feature dropped in `005`. Verified against a live copy: all row counts and the 371 backfilled `published_at` values unchanged, `/api/stories` and `/api/fetch-runs` still serve. **This migration is destructive and not reversible** — rolling back to an image older than `007` will break, since the old code still selects those columns.
- **Image pipeline removed (2026-07-29)**: `StoryCard.tsx` was orphaned — `HeadlinesPage` renders `StoryRow` only, nothing imported `StoryCard`, and it was the sole consumer of `image_url`. All 491 stories carried an `image_url` that was never displayed, costing ~25 extra page fetches + BeautifulSoup parses per run and feeding the OOM. Deleted: `utils/image_extractor.py`, `components/StoryCard.tsx`, the `fetch_images()` calls in `aggregator.run_once()` and `sources.reconcile`, the per-source image scraping in reddit/techmeme/rss_generic/hackernews, `Story.image_url`, and the field from the API response and `api.ts`. `hackernews._fetch_summary()` still fetches each page — it also extracts the summary, which *is* used. The `stories.image_url` column was dropped shortly after by migration `007`, so restoring a card view would mean re-scraping thumbnails from scratch.

## Related Projects
- `../ai-podcast` — original source; kept unchanged as the podcast version
- `../pihole-helm` — Helm chart conventions used here (`_helpers.tpl`, `Recreate` strategy, lean values, Traefik ingress + cert-manager)
- `../comptainer` — CI/CD pattern used here (`ubuntu-latest` → `arc-runner-set`, `docker/build-push-action@v7`)
- `../hankel-ai.github.io` — portfolio that embeds `/embed` via a Hugo shortcode
- `../cert-issuer-hankel` — defines the `letsencrypt-hankel` ClusterIssuer
