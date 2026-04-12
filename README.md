# ai-news

Self-hosted AI headlines aggregator. Fetches from Hacker News, RSS feeds (OpenAI, Anthropic, Google, Hugging Face, Ars Technica, MIT Tech Review, Simon Willison, The Verge, Thomas Wiegold), Reddit, Techmeme, implicator.ai, Claude Blog — on a schedule you set in the UI. Keeps a persistent history so you can browse any time. Runs as a single container on K3s via Helm.

Live at `https://news.hankel.ai`. Embedded inline into the [hankel.ai](https://hankel.ai) portfolio via a Hugo shortcode that iframes `/embed`.

## Quick start — local development

```bash
# Backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir backend

# Frontend (separate shell, proxies /api to :8000)
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

## Deployment

CI builds `ghcr.io/hankel-ai/ai-news:${sha}` on every push to `main`, then runs `helm upgrade --install` via a self-hosted in-cluster runner. See `.github/workflows/build-and-deploy.yml` and `helm/ai-news/`.

## Configuration

Everything is configurable from the **Settings** tab in the running app — sources, schedule frequency, retention, display options. First-run defaults are seeded from `helm/ai-news/templates/configmap-seed.yaml`.

## See also

- `CLAUDE.md` — architecture notes, gotchas, conventions
- `helm/ai-news/README.md` — chart values reference
