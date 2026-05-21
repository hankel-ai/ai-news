from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key

    async def complete(self, prompt: str, system: str = "") -> str:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        try:
            kwargs: dict = {
                "model": self._model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            message = await client.messages.create(**kwargs)
            return message.content[0].text
        finally:
            await client.close()
