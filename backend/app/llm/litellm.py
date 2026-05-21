import httpx
from .base import LLMProvider


class LiteLLMProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, api_key: str = "", client: httpx.AsyncClient | None = None):
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
