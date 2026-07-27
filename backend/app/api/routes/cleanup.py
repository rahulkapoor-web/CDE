import asyncio
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.mapping import MigrationProject
from app.models.cleanup import CleanupJob
from app.schemas.cleanup import CleanupJobCreate, CleanupJobResponse
from app.services.cleanup_engine import execute_cleanup, get_cleanup_order

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


@router.get("/hierarchy")
async def get_hierarchy(user: User = Depends(get_current_user)):
    """Return the object cleanup hierarchy (deletion order)."""
    return get_cleanup_order()


@router.post("/jobs", response_model=CleanupJobResponse)
async def create_cleanup_job(
    data: CleanupJobCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new cleanup job."""
    project = await db.get(MigrationProject, data.project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if data.filter_mode == "country" and not data.country_code:
        raise HTTPException(status_code=400, detail="Country code required for country filter mode")

    job = CleanupJob(
        project_id=data.project_id,
        user_id=user.id,
        filter_mode=data.filter_mode,
        country_code=data.country_code,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Run in background thread
    job_id = job.id

    def _run():
        asyncio.run(execute_cleanup(job_id))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return job


@router.get("/jobs", response_model=list[CleanupJobResponse])
async def list_cleanup_jobs(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List cleanup jobs for a project."""
    result = await db.execute(
        select(CleanupJob)
        .where(CleanupJob.project_id == project_id, CleanupJob.user_id == user.id)
        .order_by(CleanupJob.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/jobs/{job_id}", response_model=CleanupJobResponse)
async def get_cleanup_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a cleanup job by ID (used for polling progress)."""
    job = await db.get(CleanupJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Cleanup job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=CleanupJobResponse)
async def cancel_cleanup_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running cleanup job."""
    job = await db.get(CleanupJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Cleanup job not found")

    if job.status not in ("running", "pending"):
        raise HTTPException(status_code=400, detail="Job is not running")

    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return job
