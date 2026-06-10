import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.connection import ConnectionProfile
from app.models.mapping import MigrationProject, ObjectMapping, FieldMapping, MatchKeyConfig
from app.schemas.mapping import (
    MigrationProjectCreate,
    MigrationProjectResponse,
    ObjectMappingCreate,
    ObjectMappingResponse,
    FieldMappingCreate,
    FieldMappingResponse,
    MatchKeyConfigCreate,
    MatchKeyConfigResponse,
    SchemaObject,
    AutoMappingSuggestion,
)
from app.services.connector_factory import build_connector
from app.services.mapping_engine import suggest_field_mappings

router = APIRouter(prefix="/projects", tags=["mappings"])


# --- Migration Projects ---

@router.get("", response_model=list[MigrationProjectResponse])
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MigrationProject).where(MigrationProject.created_by == user.id)
    )
    return result.scalars().all()


@router.post("", response_model=MigrationProjectResponse)
async def create_project(
    data: MigrationProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = MigrationProject(
        name=data.name,
        description=data.description,
        source_connection_id=data.source_connection_id,
        target_connection_id=data.target_connection_id,
        created_by=user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=MigrationProjectResponse)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()
    return {"detail": "Deleted"}


# --- Schema Discovery ---

@router.get("/{project_id}/schema/source", response_model=list[dict])
async def list_source_objects(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    profile = await db.get(ConnectionProfile, project.source_connection_id)
    connector = build_connector(profile)
    return connector.list_objects()


@router.get("/{project_id}/schema/target", response_model=list[dict])
async def list_target_objects(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    profile = await db.get(ConnectionProfile, project.target_connection_id)
    connector = build_connector(profile)
    return connector.list_objects()


@router.get("/{project_id}/schema/source/{object_name}", response_model=SchemaObject)
async def describe_source_object(
    project_id: str,
    object_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    profile = await db.get(ConnectionProfile, project.source_connection_id)
    connector = build_connector(profile)
    return connector.describe_object(object_name)


@router.get("/{project_id}/schema/target/{object_name}", response_model=SchemaObject)
async def describe_target_object(
    project_id: str,
    object_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    profile = await db.get(ConnectionProfile, project.target_connection_id)
    connector = build_connector(profile)
    return connector.describe_object(object_name)


# --- Object Mappings ---

@router.get("/{project_id}/object-mappings", response_model=list[ObjectMappingResponse])
async def list_object_mappings(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ObjectMapping).where(ObjectMapping.project_id == project_id)
    )
    return result.scalars().all()


@router.post("/{project_id}/object-mappings", response_model=ObjectMappingResponse)
async def create_object_mapping(
    project_id: str,
    data: ObjectMappingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    mapping = ObjectMapping(
        project_id=project_id,
        source_object=data.source_object,
        target_object=data.target_object,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return mapping


@router.delete("/{project_id}/object-mappings/{mapping_id}")
async def delete_object_mapping(
    project_id: str,
    mapping_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mapping = await db.get(ObjectMapping, mapping_id)
    if not mapping or mapping.project_id != project_id:
        raise HTTPException(status_code=404, detail="Mapping not found")
    await db.delete(mapping)
    await db.commit()
    return {"detail": "Deleted"}


# --- Auto-Mapping ---

@router.post(
    "/{project_id}/object-mappings/{mapping_id}/auto-map",
    response_model=list[AutoMappingSuggestion],
)
async def auto_map_fields(
    project_id: str,
    mapping_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Auto-discover field mappings between source and target objects."""
    mapping = await db.get(ObjectMapping, mapping_id)
    if not mapping or mapping.project_id != project_id:
        raise HTTPException(status_code=404, detail="Mapping not found")

    project = await db.get(MigrationProject, project_id)
    source_profile = await db.get(ConnectionProfile, project.source_connection_id)
    target_profile = await db.get(ConnectionProfile, project.target_connection_id)

    source_connector = build_connector(source_profile)
    target_connector = build_connector(target_profile)

    source_schema = source_connector.describe_object(mapping.source_object)
    target_schema = target_connector.describe_object(mapping.target_object)

    suggestions = suggest_field_mappings(source_schema.fields, target_schema.fields)
    return suggestions


@router.post("/{project_id}/object-mappings/{mapping_id}/apply-suggestions")
async def apply_mapping_suggestions(
    project_id: str,
    mapping_id: str,
    suggestions: list[AutoMappingSuggestion],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply auto-mapping suggestions as field mappings."""
    mapping = await db.get(ObjectMapping, mapping_id)
    if not mapping or mapping.project_id != project_id:
        raise HTTPException(status_code=404, detail="Mapping not found")

    created = []
    for s in suggestions:
        fm = FieldMapping(
            object_mapping_id=mapping_id,
            source_field=s.source_field,
            target_field=s.target_field,
            source_field_type=s.source_field_type,
            target_field_type=s.target_field_type,
            confidence_score=s.confidence_score,
            is_auto_mapped=True,
        )
        db.add(fm)
        created.append(fm)

    await db.commit()
    return {"detail": f"Applied {len(created)} field mappings"}


# --- Field Mappings ---

@router.get(
    "/{project_id}/object-mappings/{mapping_id}/field-mappings",
    response_model=list[FieldMappingResponse],
)
async def list_field_mappings(
    project_id: str,
    mapping_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FieldMapping).where(FieldMapping.object_mapping_id == mapping_id)
    )
    return result.scalars().all()


@router.post(
    "/{project_id}/object-mappings/{mapping_id}/field-mappings",
    response_model=FieldMappingResponse,
)
async def create_field_mapping(
    project_id: str,
    mapping_id: str,
    data: FieldMappingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fm = FieldMapping(
        object_mapping_id=mapping_id,
        source_field=data.source_field,
        target_field=data.target_field,
        source_field_type=data.source_field_type,
        target_field_type=data.target_field_type,
        transformation=data.transformation,
        is_confirmed=True,
    )
    db.add(fm)
    await db.commit()
    await db.refresh(fm)
    return fm


@router.delete("/{project_id}/object-mappings/{mapping_id}/field-mappings/{field_mapping_id}")
async def delete_field_mapping(
    project_id: str,
    mapping_id: str,
    field_mapping_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fm = await db.get(FieldMapping, field_mapping_id)
    if not fm or fm.object_mapping_id != mapping_id:
        raise HTTPException(status_code=404, detail="Field mapping not found")
    await db.delete(fm)
    await db.commit()
    return {"detail": "Deleted"}


# --- Match Keys ---

@router.get(
    "/{project_id}/object-mappings/{mapping_id}/match-keys",
    response_model=list[MatchKeyConfigResponse],
)
async def list_match_keys(
    project_id: str,
    mapping_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MatchKeyConfig)
        .where(MatchKeyConfig.object_mapping_id == mapping_id)
        .order_by(MatchKeyConfig.key_order)
    )
    return result.scalars().all()


@router.post(
    "/{project_id}/object-mappings/{mapping_id}/match-keys",
    response_model=MatchKeyConfigResponse,
)
async def create_match_key(
    project_id: str,
    mapping_id: str,
    data: MatchKeyConfigCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mk = MatchKeyConfig(
        object_mapping_id=mapping_id,
        source_field=data.source_field,
        target_field=data.target_field,
        key_order=data.key_order,
    )
    db.add(mk)
    await db.commit()
    await db.refresh(mk)
    return mk


@router.delete("/{project_id}/object-mappings/{mapping_id}/match-keys/{key_id}")
async def delete_match_key(
    project_id: str,
    mapping_id: str,
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mk = await db.get(MatchKeyConfig, key_id)
    if not mk or mk.object_mapping_id != mapping_id:
        raise HTTPException(status_code=404, detail="Match key not found")
    await db.delete(mk)
    await db.commit()
    return {"detail": "Deleted"}


# --- Export / Import Mappings ---

@router.get("/{project_id}/object-mappings/{mapping_id}/export")
async def export_mappings(
    project_id: str,
    mapping_id: str,
    format: str = "csv",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export field mappings as CSV or Excel."""
    result = await db.execute(
        select(FieldMapping).where(FieldMapping.object_mapping_id == mapping_id)
    )
    mappings = result.scalars().all()

    data = [
        {
            "source_field": m.source_field,
            "target_field": m.target_field,
            "source_field_type": m.source_field_type,
            "target_field_type": m.target_field_type,
            "confidence_score": m.confidence_score,
            "is_auto_mapped": m.is_auto_mapped,
            "is_confirmed": m.is_confirmed,
        }
        for m in mappings
    ]
    df = pd.DataFrame(data)
    buf = io.BytesIO()

    if format == "excel":
        df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=mappings_{mapping_id}.xlsx"},
        )
    else:
        csv_str = df.to_csv(index=False)
        return StreamingResponse(
            io.BytesIO(csv_str.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=mappings_{mapping_id}.csv"},
        )


@router.post("/{project_id}/object-mappings/{mapping_id}/import")
async def import_mappings(
    project_id: str,
    mapping_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import field mappings from CSV or Excel."""
    content = await file.read()
    buf = io.BytesIO(content)

    if file.filename and file.filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(buf, engine="openpyxl")
    else:
        df = pd.read_csv(buf)

    required_cols = {"source_field", "target_field"}
    if not required_cols.issubset(set(df.columns)):
        raise HTTPException(
            status_code=400,
            detail=f"File must contain columns: {required_cols}",
        )

    created = 0
    for _, row in df.iterrows():
        fm = FieldMapping(
            object_mapping_id=mapping_id,
            source_field=row["source_field"],
            target_field=row["target_field"],
            source_field_type=row.get("source_field_type"),
            target_field_type=row.get("target_field_type"),
            is_confirmed=True,
        )
        db.add(fm)
        created += 1

    await db.commit()
    return {"detail": f"Imported {created} field mappings"}
