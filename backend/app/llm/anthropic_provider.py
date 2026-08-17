"""Anthropic Claude adapter.

Supports two auth modes:
  1. Direct API key via ANTHROPIC_API_KEY.
  2. Gateway/proxy via ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL (+ optional
     ANTHROPIC_CUSTOM_HEADERS), for Anthropic-compatible gateways that inject
     the real credentials upstream.
"""

from app.core.config import settings
from app.llm.base import ImageInput, LLMProvider, LLMResult


def _parse_custom_headers(raw: str) -> dict[str, str]:
    """Parse ANTHROPIC_CUSTOM_HEADERS.

    Format: one ``Name: value`` pair per line. Only the first ": " on each line
    is treated as the separator so header values may themselves contain colons
    (e.g. JSON payloads used by some gateways).
    """
    headers: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        name = name.strip()
        value = value.strip()
        if name:
            headers[name] = value
    return headers


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        # Imported lazily so the app can start without the key in other modes.
        from anthropic import AsyncAnthropic

        self._model = settings.ANTHROPIC_MODEL

        if settings.ANTHROPIC_API_KEY:
            self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        elif settings.ANTHROPIC_AUTH_TOKEN and settings.ANTHROPIC_BASE_URL:
            # Pass api_key=None (not "") so the SDK does not emit an empty
            # X-Api-Key header that would shadow the bearer token auth.
            client_kwargs: dict = {
                "api_key": None,
                "auth_token": settings.ANTHROPIC_AUTH_TOKEN,
                "base_url": settings.ANTHROPIC_BASE_URL,
            }
            if settings.ANTHROPIC_CUSTOM_HEADERS:
                headers = _parse_custom_headers(settings.ANTHROPIC_CUSTOM_HEADERS)
                if headers:
                    client_kwargs["default_headers"] = headers
            self._client = AsyncAnthropic(**client_kwargs)
        else:
            raise RuntimeError(
                "Anthropic is not configured: set ANTHROPIC_API_KEY, or "
                "ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL for a gateway."
            )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: list[ImageInput] | None = None,
        max_tokens: int = 8000,
        temperature: float = 0.0,
    ) -> LLMResult:
        if images:
            content: list[dict] = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.media_type,
                        "data": img.data,
                    },
                }
                for img in images
            ]
            content.append({"type": "text", "text": user_prompt})
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": user_prompt}]

        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        return LLMResult(text=text, model=self._model, provider=self.name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "Anthropic provider does not supply embeddings; set EMBEDDING_PROVIDER=openai."
        )
