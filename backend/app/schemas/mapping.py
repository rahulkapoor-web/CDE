from datetime import datetime
from pydantic import BaseModel


class MigrationProjectCreate(BaseModel):
    name: str
    description: str | None = None
    source_connection_id: str
    target_connection_id: str


class MigrationProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    source_connection_id: str
    target_connection_id: str
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ObjectMappingCreate(BaseModel):
    source_object: str
    target_object: str


class ObjectMappingResponse(BaseModel):
    id: str
    project_id: str
    source_object: str
    target_object: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class FieldMappingCreate(BaseModel):
    source_field: str
    target_field: str
    source_field_type: str | None = None
    target_field_type: str | None = None
    transformation: dict | None = None


class FieldMappingResponse(BaseModel):
    id: str
    object_mapping_id: str
    source_field: str
    target_field: str
    source_field_type: str | None = None
    target_field_type: str | None = None
    transformation: dict | None = None
    confidence_score: float | None = None
    is_auto_mapped: bool
    is_confirmed: bool

    model_config = {"from_attributes": True}


class MatchKeyConfigCreate(BaseModel):
    source_field: str
    target_field: str
    key_order: int = 0


class MatchKeyConfigResponse(BaseModel):
    id: str
    object_mapping_id: str
    source_field: str
    target_field: str
    key_order: int

    model_config = {"from_attributes": True}


class SchemaField(BaseModel):
    name: str
    label: str
    field_type: str
    is_required: bool = False
    is_unique: bool = False
    length: int | None = None
    picklist_values: list[str] | None = None
    reference_to: str | None = None


class SchemaObject(BaseModel):
    name: str
    label: str
    fields: list[SchemaField]
    record_count: int | None = None


class AutoMappingSuggestion(BaseModel):
    source_field: str
    target_field: str
    source_field_type: str
    target_field_type: str
    confidence_score: float
    match_reason: str
