from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import auth, connections, mappings, validation, cleanup

app = FastAPI(
    title=settings.APP_NAME,
    description="IQVIA OCEP to Veeva Vault CRM migration validation utility",
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
app.include_router(mappings.router, prefix="/api")
app.include_router(validation.router, prefix="/api")
app.include_router(cleanup.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
