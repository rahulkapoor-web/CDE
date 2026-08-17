"""Provider selection based on configuration."""

from app.core.config import settings
from app.llm.base import LLMProvider


def get_llm_provider(name: str | None = None) -> LLMProvider:
    provider = (name or settings.LLM_PROVIDER).lower()
    if provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {provider}")


def get_embedding_provider() -> LLMProvider | None:
    provider = settings.EMBEDDING_PROVIDER.lower()
    if provider == "none":
        return None
    if provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(f"Unknown embedding provider: {provider}")
