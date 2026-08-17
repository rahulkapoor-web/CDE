"""LSC guide retrieval (RAG) with a portable cosine-similarity fallback.

Embeddings are stored as JSON arrays on GuideDocument. Similarity is computed in
Python so the feature works whether or not pgvector is installed. When no guide
documents exist, retrieval returns an empty string and the engine falls back to
model knowledge.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.factory import get_embedding_provider
from app.models.guide import GuideDocument

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _chunk(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


async def ingest_document(
    db: AsyncSession,
    *,
    content: str,
    module: str | None = None,
    section: str | None = None,
    source: str | None = None,
) -> int:
    """Chunk, embed (if provider available), and store a guide document.

    Returns the number of chunks stored.
    """
    chunks = _chunk(content)
    embed_provider = None
    try:
        embed_provider = get_embedding_provider()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding provider unavailable: %s", exc)

    embeddings: list[list[float] | None] = [None] * len(chunks)
    if embed_provider is not None:
        try:
            embeddings = await embed_provider.embed(chunks)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding failed, storing without vectors: %s", exc)
            embeddings = [None] * len(chunks)

    for chunk_text, emb in zip(chunks, embeddings):
        db.add(
            GuideDocument(
                module=module,
                section=section,
                source=source,
                content=chunk_text,
                embedding=emb,
            )
        )
    await db.commit()
    return len(chunks)


async def retrieve_context(db: AsyncSession, query: str, top_k: int = 5) -> str:
    """Return concatenated top-k relevant guide excerpts, or '' if none stored."""
    result = await db.execute(select(GuideDocument))
    docs = result.scalars().all()
    if not docs:
        return ""

    query_emb: list[float] | None = None
    try:
        provider = get_embedding_provider()
        if provider is not None:
            query_emb = (await provider.embed([query]))[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Query embedding failed: %s", exc)

    if query_emb is not None and any(d.embedding for d in docs):
        scored = [
            (_cosine(query_emb, d.embedding), d) for d in docs if d.embedding
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [d for _, d in scored[:top_k]]
    else:
        # No embeddings available — naive keyword overlap fallback.
        terms = {t.lower() for t in query.split() if len(t) > 3}
        scored = [
            (sum(1 for t in terms if t in d.content.lower()), d) for d in docs
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [d for _, d in scored[:top_k]]

    parts = []
    for d in top:
        header = " / ".join(p for p in [d.module, d.section] if p)
        parts.append(f"[{header or d.source or 'LSC Guide'}]\n{d.content}")
    return "\n\n".join(parts)
