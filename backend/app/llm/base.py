"""LLM provider interface shared by all adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ImageInput:
    """A base64-encoded image to include alongside the text prompt.

    ``data`` is the raw base64 string (no ``data:`` URI prefix). ``media_type``
    is a MIME type such as ``image/png`` or ``image/jpeg``.
    """

    media_type: str
    data: str


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
        images: list[ImageInput] | None = None,
        max_tokens: int = 8000,
        temperature: float = 0.0,
    ) -> LLMResult:
        """Return a completion. Implementations must request JSON-only output
        where the caller's prompt asks for it. ``images`` are optional visual
        inputs (e.g. a design export) for multimodal models."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for the given texts (may raise if unsupported)."""
