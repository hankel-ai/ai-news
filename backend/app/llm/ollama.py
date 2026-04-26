import httpx
from .base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client

    async def complete(self, prompt: str, system: str = "") -> str:
        client = self._client or httpx.AsyncClient(timeout=120)
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        finally:
            if not self._client:
                await client.aclose()
