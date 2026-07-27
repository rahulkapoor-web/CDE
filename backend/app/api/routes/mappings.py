import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
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


# --- Bulk Import from Migration Mapping Sheet ---

@router.post("/{project_id}/import-mapping-sheet")
async def import_mapping_sheet(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a full migration mapping workbook (Excel).

    Parses all sheets whose name starts with 'Mapping' and contains 'Fields'.
    Expects the standard Roche/IQVIA migration sheet format with:
    - Source object/field info in the left columns
    - Target object/field info in the middle columns
    - Migration scope flags in the right columns

    Creates object mappings, field mappings, and match keys automatically.
    """
    project = await db.get(MigrationProject, project_id)
    if not project or project.created_by != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    buf = io.BytesIO(content)

    import openpyxl
    wb = openpyxl.load_workbook(buf, read_only=True, data_only=True)

    stats = {
        "object_mappings_created": 0,
        "field_mappings_created": 0,
        "sheets_processed": [],
        "errors": [],
    }

    # Find all field mapping sheets — include any sheet with "Mapping" in the name
    # except the object-level "Mapping Objects" sheet
    field_sheets = [
        s for s in wb.sheetnames
        if "Mapping" in s and s.strip() != "Mapping Objects"
    ]

    for sheet_name in field_sheets:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 3:
            stats["errors"].append(f"{sheet_name}: too few rows, skipped")
            continue

        # Find header row — look for a row containing 'QualifiedApiName' or 'Field Name'
        header_row_idx = None
        headers = []
        for idx, row in enumerate(rows[:5]):
            row_strs = [str(c).strip().lower() if c else "" for c in row]
            if "qualifiedapiname" in row_strs or "field name" in row_strs:
                header_row_idx = idx
                headers = [str(c).strip() if c else "" for c in row]
                break

        if header_row_idx is None:
            # Try second row as header (common pattern)
            header_row_idx = 1
            headers = [str(c).strip() if c else "" for c in rows[1]]

        # Map column indices by looking for known column names.
        # Use first match only — sheets often have a reference target field
        # list in later columns that would overwrite the actual mapping columns.
        col_map = {}
        for i, h in enumerate(headers):
            hl = h.lower().replace(" ", "").replace("_", "")
            if hl in ("entityapiname", "sourceobject", "sourceobjectapiname"):
                col_map.setdefault("source_object", i)
            elif hl in ("qualifiedapiname", "sourcefield", "sourcefieldapiname", "sourceapiname"):
                col_map.setdefault("source_field", i)
            elif hl in ("datatype", "sourcedatatype", "sourcefieldtype", "sourcetype"):
                col_map.setdefault("source_type", i)
            elif hl in ("objectname", "targetobject", "targetobjectapiname", "targetobjectname"):
                col_map.setdefault("target_object", i)
            elif hl in ("fieldname", "targetfield", "targetfieldapiname", "targetfieldname"):
                col_map.setdefault("target_field", i)
            elif hl in ("fieldtype", "targetdatatype", "targetfieldtype", "targettype"):
                col_map.setdefault("target_type", i)
            elif hl in ("relevantformigration", "inmigrationscope", "inrochemigrationscope", "migrationscope"):
                col_map.setdefault("in_scope", i)
            elif hl in ("transformationrequired",):
                col_map.setdefault("transformation_required", i)
            elif hl in ("transformationlogic",):
                col_map.setdefault("transformation_logic", i)

        if "source_field" not in col_map or "target_field" not in col_map:
            stats["errors"].append(
                f"{sheet_name}: could not find source_field/target_field columns, skipped"
            )
            continue

        # Process data rows
        object_mapping_cache = {}  # (source_obj, target_obj) -> ObjectMapping
        sheet_field_count = 0

        for row in rows[header_row_idx + 1:]:
            if not row or all(c is None for c in row):
                continue

            def get_col(key):
                idx = col_map.get(key)
                if idx is None or idx >= len(row):
                    return None
                val = row[idx]
                return str(val).strip() if val else None

            source_field = get_col("source_field")
            target_field = get_col("target_field")

            if not source_field or not target_field:
                continue

            # Check migration scope filter
            in_scope = get_col("in_scope")
            if in_scope and in_scope.lower() in ("no", "n", "false", "out of scope"):
                continue

            source_object = get_col("source_object")
            target_object = get_col("target_object")

            if not source_object or not target_object:
                continue

            # Get or create object mapping
            om_key = (source_object, target_object)
            if om_key not in object_mapping_cache:
                # Check if it already exists in DB — use first match if duplicates exist
                existing = await db.execute(
                    select(ObjectMapping).where(
                        ObjectMapping.project_id == project_id,
                        ObjectMapping.source_object == source_object,
                        ObjectMapping.target_object == target_object,
                    )
                )
                om = existing.scalars().first()
                if not om:
                    om = ObjectMapping(
                        project_id=project_id,
                        source_object=source_object,
                        target_object=target_object,
                    )
                    db.add(om)
                    await db.flush()
                    stats["object_mappings_created"] += 1
                else:
                    # Clear existing field mappings — sheet import replaces them
                    await db.execute(
                        delete(FieldMapping).where(
                            FieldMapping.object_mapping_id == om.id
                        )
                    )
                    await db.flush()
                object_mapping_cache[om_key] = om

            om = object_mapping_cache[om_key]

            # Build transformation info
            transformation = None
            tx_required = get_col("transformation_required")
            tx_logic = get_col("transformation_logic")
            if tx_required and tx_required.lower() in ("yes", "y", "true"):
                transformation = {"required": True, "logic": tx_logic or ""}

            # Create field mapping
            fm = FieldMapping(
                object_mapping_id=om.id,
                source_field=source_field,
                target_field=target_field,
                source_field_type=get_col("source_type"),
                target_field_type=get_col("target_type"),
                transformation=transformation,
                is_auto_mapped=False,
                is_confirmed=True,
            )
            db.add(fm)
            sheet_field_count += 1

        stats["field_mappings_created"] += sheet_field_count
        stats["sheets_processed"].append(f"{sheet_name} ({sheet_field_count} fields)")

    await db.commit()

    return {
        "detail": (
            f"Imported {stats['object_mappings_created']} object mappings, "
            f"{stats['field_mappings_created']} field mappings "
            f"from {len(stats['sheets_processed'])} sheets"
        ),
        "stats": stats,
    }
