from datetime import datetime
from pydantic import BaseModel


class ValidationRunCreate(BaseModel):
    project_id: str
    object_mapping_ids: list[str] | None = None  # None = all active mappings
    mode: str = "auto"  # auto, realtime, batch


class ValidationRunResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    status: str
    mode: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    object_mapping_ids: list[str] | None = None

    model_config = {"from_attributes": True}


class ValidationSummaryResponse(BaseModel):
    id: str
    validation_run_id: str
    object_mapping_id: str
    source_object: str
    target_object: str
    source_count: int
    target_count: int
    matched_count: int
    mismatched_count: int
    missing_in_target_count: int
    missing_in_source_count: int
    match_percentage: float
    status: str
    error_message: str | None = None

    model_config = {"from_attributes": True}


class ValidationDetailResponse(BaseModel):
    id: str
    summary_id: str
    match_key_value: str
    status: str
    field_diffs: dict | None = None

    model_config = {"from_attributes": True}


class ValidationDetailPage(BaseModel):
    items: list[ValidationDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
