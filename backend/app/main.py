"""ONA — AI Planning Engine FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, connections, guide, planning
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="Turns JIRA requirements into ordered, schema-validated "
    "Salesforce Life Sciences Cloud change plans.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(connections.router, prefix="/api")
app.include_router(planning.router, prefix="/api")
app.include_router(guide.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "llm_provider": settings.LLM_PROVIDER,
    }
