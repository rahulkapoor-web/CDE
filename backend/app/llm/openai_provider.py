"""OpenAI adapter (completions + embeddings)."""

from app.core.config import settings
from app.llm.base import ImageInput, LLMProvider, LLMResult


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL
        self._embed_model = settings.EMBEDDING_MODEL

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
            user_content: list[dict] = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img.media_type};base64,{img.data}"
                    },
                }
                for img in images
            ]
            user_content.append({"type": "text", "text": user_prompt})
            user_message: dict = {"role": "user", "content": user_content}
        else:
            user_message = {"role": "user", "content": user_prompt}

        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                user_message,
            ],
        )
        text = resp.choices[0].message.content or ""
        return LLMResult(text=text, model=self._model, provider=self.name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(
            model=self._embed_model, input=texts
        )
        return [item.embedding for item in resp.data]
