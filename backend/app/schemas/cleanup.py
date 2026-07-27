from datetime import datetime
from pydantic import BaseModel


class CleanupJobCreate(BaseModel):
    project_id: str
    filter_mode: str = "legacy_crm_id"  # legacy_crm_id or country
    country_code: str | None = None


class CleanupJobResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    status: str
    filter_mode: str
    country_code: str | None = None
    total_steps: int = 0
    completed_steps: int = 0
    current_object: str | None = None
    current_phase: str | None = None
    records_found: int = 0
    records_deleted: int = 0
    step_results: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
