from .base import LLMProvider
from .ollama import OllamaProvider
from .anthropic_provider import AnthropicProvider
from .litellm import LiteLLMProvider


def get_provider(provider_name: str, model: str, base_url: str, api_key: str) -> LLMProvider:
    if provider_name == "ollama":
        return OllamaProvider(base_url=base_url or "http://localhost:11434", model=model)
    elif provider_name == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    elif provider_name == "litellm":
        return LiteLLMProvider(base_url=base_url, model=model, api_key=api_key)
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
