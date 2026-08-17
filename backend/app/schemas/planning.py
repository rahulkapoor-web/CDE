"""Schemas for context gathering and plan generation requests/responses."""

from datetime import datetime

from pydantic import BaseModel


class GatherContextRequest(BaseModel):
    jira_connection_id: int | None = None
    github_connection_id: int | None = None
    salesforce_connection_id: int | None = None
    jira_ticket_id: str | None = None
    github_repo: str | None = None  # owner/repo override
    github_branch: str | None = None
    sfdx_path: str | None = None  # local SFDX project path for metadata parsing


class PlanningContext(BaseModel):
    """Consolidated, editable context passed to the planning engine."""

    jira_ticket_id: str = ""
    jira_summary: str = ""
    jira_description: str = ""
    jira_acceptance_criteria: str = ""
    jira_type: str = ""
    jira_priority: str = ""

    sf_org_edition: str = ""
    lsc_modules: list[str] = []
    installed_packages: list[str] = []
    metadata_objects: list[str] = []
    metadata_fields: list[str] = []
    metadata_flows: list[str] = []
    metadata_apex_classes: list[str] = []
    metadata_permission_sets: list[str] = []

    github_branch: str = ""
    github_recent_commits: list[str] = []
    github_open_prs: list[str] = []


class GeneratePlanRequest(BaseModel):
    context: PlanningContext


class PlanOut(BaseModel):
    id: int
    jira_ticket: str
    summary: str | None
    status: str
    provider: str | None
    model: str | None
    context_snapshot: dict
    plan_json: dict
    created_at: datetime

    class Config:
        from_attributes = True


class PlanSummaryOut(BaseModel):
    id: int
    jira_ticket: str
    summary: str | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
