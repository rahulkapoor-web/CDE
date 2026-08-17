"""LSC guide document ingestion for RAG grounding."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.guide import GuideDocument
from app.models.user import User
from app.services.rag import ingest_document

router = APIRouter(prefix="/guide", tags=["guide"])


class IngestRequest(BaseModel):
    content: str
    module: str | None = None
    section: str | None = None
    source: str | None = None


class IngestResult(BaseModel):
    chunks_stored: int


@router.post("/ingest", response_model=IngestResult)
async def ingest(
    payload: IngestRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IngestResult:
    count = await ingest_document(
        db,
        content=payload.content,
        module=payload.module,
        section=payload.section,
        source=payload.source,
    )
    return IngestResult(chunks_stored=count)


@router.get("/status")
async def status(
    _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    result = await db.execute(select(func.count()).select_from(GuideDocument))
    return {"documents": result.scalar_one()}
