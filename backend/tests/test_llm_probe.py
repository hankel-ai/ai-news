import json

import httpx
import pytest

from app.llm.probe import check_llm


class FakeTransport(httpx.AsyncBaseTransport):
    """Routes by path: /api/tags and /v1/models return canned responses; others raise."""

    def __init__(self, tags_body: dict | None = None, models_body: dict | None = None,
                 tags_status: int = 200, models_status: int = 200):
        self._tags_body = tags_body
        self._models_body = models_body
        self._tags_status = tags_status
        self._models_status = models_status
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        if request.url.path == "/api/tags":
            if self._tags_body is None:
                raise httpx.ConnectError("connection refused")
            return httpx.Response(self._tags_status, content=json.dumps(self._tags_body).encode())
        if request.url.path == "/v1/models":
            if self._models_body is None:
                raise httpx.ConnectError("connection refused")
            return httpx.Response(self._models_status, content=json.dumps(self._models_body).encode())
        raise AssertionError(f"unexpected path {request.url.path}")


@pytest.mark.asyncio
async def test_ollama_healthy_with_model_present():
    transport = FakeTransport(tags_body={"models": [{"name": "llama3.2:latest"}, {"name": "qwen3:8b"}]})
    ok, reason = await check_llm("ollama", "llama3.2", "http://localhost:11434", "", client=httpx.AsyncClient(transport=transport))
    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_ollama_unreachable():
    transport = FakeTransport()  # /api/tags raises ConnectError
    ok, reason = await check_llm("ollama", "llama3.2", "http://localhost:11434", "", client=httpx.AsyncClient(transport=transport))
    assert ok is False
    assert "ConnectError" in reason


@pytest.mark.asyncio
async def test_ollama_model_missing():
    transport = FakeTransport(tags_body={"models": [{"name": "qwen3:8b"}]})
    ok, reason = await check_llm("ollama", "llama3.2", "http://localhost:11434", "", client=httpx.AsyncClient(transport=transport))
    assert ok is False
    assert "llama3.2" in reason
    assert "not" in reason.lower()


@pytest.mark.asyncio
async def test_ollama_model_missing_tolerates_version_suffix():
    """Configured 'llama3.2' should match server's 'llama3.2:latest' and vice versa."""
    transport = FakeTransport(tags_body={"models": [{"name": "llama3.2:latest"}]})
    ok, _ = await check_llm("ollama", "llama3.2", "http://localhost:11434", "", client=httpx.AsyncClient(transport=transport))
    assert ok is True
    transport2 = FakeTransport(tags_body={"models": [{"name": "llama3.2"}]})
    ok2, _ = await check_llm("ollama", "llama3.2:latest", "http://localhost:11434", "", client=httpx.AsyncClient(transport=transport2))
    assert ok2 is True


@pytest.mark.asyncio
async def test_ollama_http_error():
    transport = FakeTransport(tags_body={"error": "boom"}, tags_status=500)
    ok, reason = await check_llm("ollama", "llama3.2", "http://localhost:11434", "", client=httpx.AsyncClient(transport=transport))
    assert ok is False
    assert "500" in reason


@pytest.mark.asyncio
async def test_anthropic_models_endpoint():
    transport = FakeTransport(models_body={"data": [{"id": "claude-sonnet-5"}]})
    ok, reason = await check_llm("anthropic", "claude-sonnet-5", "https://api.anthropic.com", "sk-test", client=httpx.AsyncClient(transport=transport))
    assert ok is True
    # request carried the auth headers
    sent = transport.requests[0]
    assert sent.headers.get("x-api-key") == "sk-test"


@pytest.mark.asyncio
async def test_anthropic_unreachable():
    transport = FakeTransport()
    ok, reason = await check_llm("anthropic", "claude-sonnet-5", "https://api.anthropic.com", "sk", client=httpx.AsyncClient(transport=transport))
    assert ok is False
    assert reason


@pytest.mark.asyncio
async def test_litellm_models_endpoint():
    transport = FakeTransport(models_body={"data": [{"id": "gpt-4"}]})
    ok, reason = await check_llm("litellm", "gpt-4", "http://localhost:4000", "sk-test", client=httpx.AsyncClient(transport=transport))
    assert ok is True


@pytest.mark.asyncio
async def test_litellm_model_missing():
    transport = FakeTransport(models_body={"data": [{"id": "other-model"}]})
    ok, reason = await check_llm("litellm", "gpt-4", "http://localhost:4000", "sk-test", client=httpx.AsyncClient(transport=transport))
    assert ok is False
    assert "gpt-4" in reason


@pytest.mark.asyncio
async def test_models_list_unparseable_counts_as_missing_model():
    """Server up but returned no parseable model list: only fail when a model was expected to match."""
    transport = FakeTransport(models_body={"data": []})
    ok, reason = await check_llm("litellm", "gpt-4", "http://localhost:4000", "sk-test", client=httpx.AsyncClient(transport=transport))
    assert ok is False
    assert "gpt-4" in reason
