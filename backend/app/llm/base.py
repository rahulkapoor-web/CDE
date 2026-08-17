"""LLM provider interface shared by all adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 8000,
        temperature: float = 0.0,
    ) -> LLMResult:
        """Return a completion. Implementations must request JSON-only output
        where the caller's prompt asks for it."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for the given texts (may raise if unsupported)."""
