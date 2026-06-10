import io
from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.user import User
from app.models.connection import ConnectionProfile
from app.models.mapping import MigrationProject, ObjectMapping
from app.models.validation import ValidationRun, ValidationSummary, ValidationDetail
from app.schemas.validation import (
    ValidationRunCreate,
    ValidationRunResponse,
    ValidationSummaryResponse,
    ValidationDetailResponse,
    ValidationDetailPage,
)
from app.services.connector_factory import build_connector
from app.services.validation_engine import run_validation_for_object
from app.workers.tasks import run_batch_validation

router = APIRouter(prefix="/validation", tags=["validation"])


@router.post("/runs", response_model=ValidationRunResponse)
async def create_validation_run(
    data: ValidationRunCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create and start a validation run.

    Mode selection:
    - auto: checks record counts and picks realtime or batch per object
    - realtime: runs inline, blocks until complete
    - batch: queues as a Celery background job
    """
    project = await db.get(MigrationProject, data.project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    run = ValidationRun(
        project_id=data.project_id,
        user_id=user.id,
        mode=data.mode,
        object_mapping_ids=data.object_mapping_ids,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if data.mode == "batch" or data.mode == "auto":
        # Queue as background job
        run.status = "queued"
        await db.commit()
        run_batch_validation.delay(run.id)
    elif data.mode == "realtime":
        # Run inline
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            source_profile = await db.get(ConnectionProfile, project.source_connection_id)
            target_profile = await db.get(ConnectionProfile, project.target_connection_id)

            if data.object_mapping_ids:
                mappings_result = await db.execute(
                    select(ObjectMapping).where(
                        ObjectMapping.id.in_(data.object_mapping_ids),
                        ObjectMapping.is_active == True,
                    )
                )
            else:
                mappings_result = await db.execute(
                    select(ObjectMapping).where(
                        ObjectMapping.project_id == data.project_id,
                        ObjectMapping.is_active == True,
                    )
                )
            object_mappings = list(mappings_result.scalars().all())

            for om in object_mappings:
                await run_validation_for_object(db, run, om, source_profile, target_profile)

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

    await db.refresh(run)
    return run


@router.get("/runs", response_model=list[ValidationRunResponse])
async def list_validation_runs(
    project_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ValidationRun).where(ValidationRun.user_id == user.id)
    if project_id:
        query = query.where(ValidationRun.project_id == project_id)
    query = query.order_by(ValidationRun.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=ValidationRunResponse)
async def get_validation_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await db.get(ValidationRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Validation run not found")
    return run


@router.get("/runs/{run_id}/summaries", response_model=list[ValidationSummaryResponse])
async def get_validation_summaries(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await db.get(ValidationRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Validation run not found")

    result = await db.execute(
        select(ValidationSummary).where(ValidationSummary.validation_run_id == run_id)
    )
    return result.scalars().all()


@router.get("/summaries/{summary_id}/details", response_model=ValidationDetailPage)
async def get_validation_details(
    summary_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    status_filter: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated validation details for a summary."""
    query = select(ValidationDetail).where(ValidationDetail.summary_id == summary_id)
    count_query = select(func.count(ValidationDetail.id)).where(
        ValidationDetail.summary_id == summary_id
    )

    if status_filter:
        query = query.where(ValidationDetail.status == status_filter)
        count_query = count_query.where(ValidationDetail.status == status_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return ValidationDetailPage(
        items=[ValidationDetailResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 0,
    )


# --- Export Reports ---

@router.get("/runs/{run_id}/export/summary")
async def export_summary_report(
    run_id: str,
    format: str = "csv",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export validation summary as CSV or Excel."""
    result = await db.execute(
        select(ValidationSummary).where(ValidationSummary.validation_run_id == run_id)
    )
    summaries = result.scalars().all()

    data = [
        {
            "source_object": s.source_object,
            "target_object": s.target_object,
            "source_count": s.source_count,
            "target_count": s.target_count,
            "matched": s.matched_count,
            "mismatched": s.mismatched_count,
            "missing_in_target": s.missing_in_target_count,
            "missing_in_source": s.missing_in_source_count,
            "match_percentage": s.match_percentage,
            "status": s.status,
        }
        for s in summaries
    ]
    return _export_dataframe(pd.DataFrame(data), f"summary_{run_id}", format)


@router.get("/summaries/{summary_id}/export/details")
async def export_detail_report(
    summary_id: str,
    status_filter: str | None = None,
    format: str = "csv",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export validation details as CSV or Excel."""
    query = select(ValidationDetail).where(ValidationDetail.summary_id == summary_id)
    if status_filter:
        query = query.where(ValidationDetail.status == status_filter)

    result = await db.execute(query)
    details = result.scalars().all()

    data = []
    for d in details:
        row = {
            "match_key_value": d.match_key_value,
            "status": d.status,
        }
        if d.field_diffs:
            for field_name, diff in d.field_diffs.items():
                row[f"{field_name}_source"] = diff.get("source")
                row[f"{field_name}_target"] = diff.get("target")
        data.append(row)

    return _export_dataframe(pd.DataFrame(data), f"details_{summary_id}", format)


def _export_dataframe(df: pd.DataFrame, filename: str, format: str):
    buf = io.BytesIO()
    if format == "excel":
        df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
        )
    else:
        csv_str = df.to_csv(index=False)
        return StreamingResponse(
            io.BytesIO(csv_str.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )
