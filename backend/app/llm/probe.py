"""Cheap LLM reachability probe used by the outage gate.

While the outage is active, scheduled runs call check_llm() instead of firing
full analysis batches at a dead/hung server. Reuse the shipped client via the
`client` kwarg for injection in tests.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 5.0


async def list_ollama_models(base_url: str, client: httpx.AsyncClient) -> list[str]:
    """Fetch installed model names. Raises on connectivity/HTTP errors."""
    r = await client.get(f"{base_url.rstrip('/')}/api/tags")
    r.raise_for_status()
    return [m.get("name") for m in r.json().get("models", []) if m.get("name")]


async def check_llm(
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    client: httpx.AsyncClient | None = None,
) -> tuple[bool, str | None]:
    """Return (ok, reason). reason is None when ok.

    Checks server reachability, and — when the server exposes a model list —
    that the configured model still exists (catches "model no longer available").
    """
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=PROBE_TIMEOUT_S)
    try:
        try:
            if provider == "ollama":
                headers = {}
                base = base_url.rstrip("/") or "http://localhost:11434"
                models = await list_ollama_models(base, client)
            else:
                # Anthropic & LiteLLM both serve GET /v1/models (OpenAI-compatible).
                base = (base_url.rstrip("/") or "https://api.anthropic.com")
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"} \
                    if provider == "anthropic" else \
                    {"Authorization": f"Bearer {api_key}"}
                r = await client.get(f"{base}/v1/models", headers=headers)
                r.raise_for_status()
                models = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}: {(e.response.text or e.response.reason_phrase)[:300]}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

        if model:
            if not models:
                # Server reachable but gave no usable model list — can't confirm the
                # configured model exists, so treat it as down (avoids firing full
                # analysis batches against a half-broken server).
                return False, f"no models listed at {base} (expected '{model}')"
            wanted = model.split(":")[0]
            names = {m.split(":")[0] for m in models}
            if wanted not in names:
                return False, f"model '{model}' not on server (available: {', '.join(models[:8])})"
        return True, None
    finally:
        if owned:
            await client.aclose()
