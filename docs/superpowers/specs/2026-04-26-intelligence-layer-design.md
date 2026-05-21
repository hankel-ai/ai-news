# AI News — Intelligence Layer Design

Date: 2026-04-26

## Overview

Add an AI-powered intelligence layer to ai-news that automatically summarizes stories, scores relevance, detects trending topics, and surfaces breaking alerts via browser push notifications. Includes a frontend redesign to a clean list layout with smart defaults.

## Goals

1. **Reduce noise** — relevance scoring pushes important stories to the top
2. **Add intelligence** — AI-generated summaries, topic tags, and trend detection
3. **Be proactive** — breaking alerts via browser push, trending banners on the homepage
4. **Improve readability** — clean list layout with expand-all toggle, replacing the card grid
5. **Stay flexible** — configurable LLM provider (Ollama, Anthropic, LiteLLM proxy)

## Architecture

### AI Analysis Pipeline

New pipeline stage: `backend/app/pipeline/analyzer.py`

Runs automatically after `aggregator.run_once()` fetches and persists stories. Processes the batch of newly persisted stories through three analysis stages in a single batched LLM call.

**Stages:**

1. **Summarize** — 1-2 sentence TL;DR per story from scraped content (or title + description if enrichment is disabled)
2. **Score** — relevance score 0-100 based on novelty, significance to the AI/tech community, actionability. Assigns 1-3 topic tags from a controlled vocabulary: `llm-release`, `funding`, `research`, `open-source`, `regulation`, `tutorial`, `infrastructure`, `product`, `acquisition`, `policy`
3. **Trend detect** — given current batch + last 24h of stories, identify topic clusters with unusually high activity. Output: topic name, story count, severity (`normal`, `trending`, `breaking`)

**Prompt design:**
- All stories in a batch sent as a JSON array of `{id, title, content}`
- System prompt requests structured JSON output: `{stories: [{id, summary, score, topics}], trends: [{topic, severity, count}]}`
- Batch size capped at 50 stories per LLM call; larger fetches chunked into multiple calls
- Trend detection runs on the final chunk with awareness of the full batch

### LLM Provider Abstraction

New module: `backend/app/llm/`

```
llm/
├── base.py          # Abstract LLMProvider: async def complete(prompt, system) -> str
├── ollama.py        # Local Ollama API (default, zero cost)
├── anthropic.py     # Claude API via Anthropic SDK
└── litellm.py       # OpenAI-compatible endpoint for LiteLLM proxy
```

- `ollama.py` — calls `POST /api/chat` on local or custom Ollama endpoint (supports system + user messages)
- `anthropic.py` — uses the Anthropic Python SDK with `llm_api_key`
- `litellm.py` — calls `POST /v1/chat/completions` (OpenAI-compatible format) via `httpx`, targeting a LiteLLM proxy at `llm_base_url`. No `openai` dependency.

Provider selected via `llm_provider` setting. Model via `llm_model`. Base URL via `llm_base_url`.

### LLM Configuration Flow

**Initial deployment:** LLM settings are seeded from environment variables on first boot (when no value exists in the settings table yet). This keeps sensitive values like API keys out of the UI for initial setup.

Environment variables (all optional, read by `config.py`):
- `LLM_PROVIDER` — `ollama` (default), `anthropic`, `litellm`
- `LLM_MODEL` — default `llama3.2`
- `LLM_BASE_URL` — e.g., `http://ollama.ollama:11434` or LiteLLM proxy URL
- `LLM_API_KEY` — API key for Anthropic or LiteLLM

**Helm chart:** `values.yaml` exposes an `llm` block. The API key is injected from a Kubernetes Secret via `secretKeyRef`, never stored in plain values.

```yaml
# values.yaml
llm:
  provider: ollama
  model: llama3.2
  baseUrl: http://ollama.ollama:11434
  apiKeySecretName: ""   # optional: name of a K8s Secret
  apiKeySecretKey: api-key
```

The deployment template maps these to env vars. If `apiKeySecretName` is set, `LLM_API_KEY` comes from the Secret; otherwise it's omitted.

**Runtime:** After first boot, all LLM settings live in the SQLite settings table and are editable via the Settings page UI. Env vars are only consulted during initial seed — changing them requires deleting the DB key to re-trigger seeding, or just updating via the UI.

### Breaking Alerts

**Backend:**
- When trend detection outputs severity `breaking`, insert into `trends` table with `notified=false`
- `GET /alerts/pending` — returns unacknowledged breaking trends
- `PUT /alerts/{id}/ack` — marks a trend as acknowledged
- Trends auto-expire after 24 hours

**Frontend:**
- Register a Service Worker for Web Push API (VAPID keys generated locally)
- Poll `GET /alerts/pending` every 60 seconds via TanStack Query `refetchInterval`
- Pending alert triggers browser push notification: topic name + story count
- Clicking notification opens the app filtered to that topic
- In-app: notification badge in header for unacknowledged alerts
- If notification permission not granted, badge still shows — push just doesn't fire

**Why polling, not WebSocket/SSE:** Single-user app, fetch cycles are 15+ minutes apart. Polling is simpler and sufficient.

## Frontend Redesign

### Layout: Clean List

Replaces the current card grid with a compact, typography-first list layout.

**Each story row:**
- Relevance score badge (color-coded: green 75+, yellow 50-74, gray <50)
- Story title (clickable, opens source URL)
- Source domain + relative time (right-aligned)
- Topic tags (below title, left-aligned with 36px indent)
- AI summary block (indented, subtle background, left border accent) — expandable

**Expand behavior:**
- Individual rows toggle on click
- "Expand all" toggle in the header bar — shows/hides all summaries at once
- Persisted via `display_expand_summaries` setting
- Viewed stories fade to 60% opacity (existing behavior preserved)

**Date grouping:** Preserved from current design (Today, Yesterday, etc.) when `display_group_by_date` is enabled.

### Sort & Filter Controls

**Sort** (dropdown in header, persisted as `display_sort_by`):
- **Relevance** (default) — `relevance_score` DESC
- **Newest** — `published_at` DESC
- **Source** — grouped by source, then relevance within each group

**Filters** (bar below header):
- **Source filter** — multi-select dropdown (existing, preserved)
- **Topic filter** — multi-select dropdown from AI-assigned topic tags
- **Score threshold** — quick presets: All / 50+ / 75+
- **Unread only** — toggle to hide viewed stories

### Smart Homepage

- Default view: sorted by relevance
- If an active breaking trend exists: dismissible banner at the top — "Trending: {topic} — {count} stories in the last {hours} hours" with a link to filter to that topic

### Settings Page Updates

**New section: AI Configuration**
- `llm_provider` — dropdown: Ollama / Anthropic / LiteLLM
- `llm_model` — text input (default: `llama3.2`)
- `llm_base_url` — text input (for custom Ollama endpoint or LiteLLM proxy URL)
- `llm_api_key` — password input (for Anthropic / LiteLLM)
- `analysis_enabled` — toggle (master switch for AI pipeline)
- `breaking_threshold` — number input (default: 3)
- "Test Connection" button — fires a simple prompt to verify LLM reachability

**Extended section: Display**
- `display_expand_summaries` — toggle
- `display_sort_by` — dropdown
- `display_score_threshold` — number (minimum score to display, default 0)

**New section: Notifications**
- `notifications_enabled` — toggle
- "Request Permission" button — triggers browser notification permission dialog

## Data Model

### Migration: `004_add_intelligence.sql`

**Alter `stories` table — add columns:**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `summary` | TEXT | NULL | AI-generated TL;DR |
| `relevance_score` | INTEGER | NULL | 0-100, NULL if not analyzed |
| `topics` | TEXT | NULL | JSON array of topic strings |
| `analyzed_at` | TIMESTAMP | NULL | When analysis ran |

**Create `trends` table:**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `topic` | TEXT | Topic cluster name |
| `severity` | TEXT | `normal`, `trending`, `breaking` |
| `story_count` | INTEGER | Stories in the cluster (24h window) |
| `detected_at` | TIMESTAMP | When trend was detected |
| `expires_at` | TIMESTAMP | Auto-expire after 24h |
| `notified` | BOOLEAN | Whether push notification was sent |

**New settings keys:**

| Key | Type | Default |
|-----|------|---------|
| `llm_provider` | TEXT | `ollama` |
| `llm_model` | TEXT | `llama3.2` |
| `llm_base_url` | TEXT | NULL |
| `llm_api_key` | TEXT | NULL |
| `analysis_enabled` | BOOLEAN | `true` |
| `breaking_threshold` | INTEGER | `3` |
| `display_expand_summaries` | BOOLEAN | `false` |
| `display_sort_by` | TEXT | `relevance` |
| `display_score_threshold` | INTEGER | `0` |
| `notifications_enabled` | BOOLEAN | `true` |

## Error Handling

**LLM unreachable or analysis disabled:**
- Stories persist normally without `summary`, `relevance_score`, or `topics`
- Frontend gracefully degrades: no score badge, no tags, no summary block
- Title + source + time still renders fully

**LLM failure during fetch:**
- Analysis stage wrapped in try/except
- Failure logged, recorded in `fetch_runs`, does not block story persistence
- Health diagnostics on Settings page show last LLM error

**Re-analysis:**
- "Re-analyze" button in fetch runs table retries analysis for all unanalyzed stories from that specific fetch run

**Notifications:**
- Browser push requires HTTPS or localhost — works in production (Traefik + cert-manager) and dev
- Trends auto-expire after 24 hours to prevent stale "breaking" badges

## API Changes

**New endpoints:**
- `GET /alerts/pending` — unacknowledged breaking trends
- `PUT /alerts/{id}/ack` — acknowledge a trend
- `POST /analyze` — manually trigger analysis on recent unanalyzed stories

**Modified endpoints:**
- `GET /stories` — new query params: `sort_by` (relevance/newest/source), `min_score` (integer), `topics` (comma-separated), `unread_only` (boolean)
- `GET /settings` / `PUT /settings` — include new AI and display settings

## Dependencies

**New Python packages:**
- `anthropic` — Anthropic SDK (only imported when provider is `anthropic`)

**No new frontend packages.** Service Worker and Web Push API are browser-native.

## Deployment Notes

- No new infrastructure required — runs on existing single-pod K3s deployment
- LLM calls add latency to fetch cycles; with Ollama on a local network this is typically 5-30s per batch
- SQLite schema migration runs automatically on pod restart (existing migration runner)
- VAPID keys generated on first startup and stored as `vapid_public_key` / `vapid_private_key` in the settings table
- `llm_api_key` is stored as plaintext in the settings table — consistent with the app's no-auth design. If this becomes a concern, move it to a Kubernetes Secret + env var
