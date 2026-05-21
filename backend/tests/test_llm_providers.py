import json
import pytest
import httpx

from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.llm.litellm import LiteLLMProvider
from app.llm import get_provider


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, response_body: dict, status_code: int = 200):
        self._body = json.dumps(response_body).encode()
        self._status = status_code

    async def handle_async_request(self, request):
        return httpx.Response(self._status, content=self._body)


@pytest.mark.asyncio
async def test_ollama_provider_sends_chat_request():
    fake_response = {"message": {"content": "Hello from Ollama"}}
    transport = FakeTransport(fake_response)
    client = httpx.AsyncClient(transport=transport)
    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2", client=client)
    result = await provider.complete("Say hello", system="You are helpful")
    assert result == "Hello from Ollama"


@pytest.mark.asyncio
async def test_litellm_provider_sends_openai_format():
    fake_response = {"choices": [{"message": {"content": "Hello from LiteLLM"}}]}
    transport = FakeTransport(fake_response)
    client = httpx.AsyncClient(transport=transport)
    provider = LiteLLMProvider(base_url="http://localhost:4000", model="gpt-4", api_key="test-key", client=client)
    result = await provider.complete("Say hello", system="You are helpful")
    assert result == "Hello from LiteLLM"


def test_get_provider_returns_ollama_by_default():
    provider = get_provider(provider_name="ollama", model="llama3.2", base_url="http://localhost:11434", api_key="")
    assert isinstance(provider, OllamaProvider)


def test_get_provider_returns_litellm():
    provider = get_provider(provider_name="litellm", model="gpt-4", base_url="http://localhost:4000", api_key="sk-test")
    assert isinstance(provider, LiteLLMProvider)


def test_get_provider_raises_on_unknown():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider(provider_name="unknown", model="x", base_url="", api_key="")
