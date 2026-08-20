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


class JiraImage(BaseModel):
    """An image attachment pulled from a JIRA ticket.

    ``data`` is base64-encoded so it round-trips through JSON and can be shown in
    the upload area and fed to the multimodal planner alongside manual uploads.
    """

    filename: str
    media_type: str
    data: str


class PlanningContext(BaseModel):
    """Consolidated, editable context passed to the planning engine."""

    jira_ticket_id: str = ""
    jira_summary: str = ""
    jira_description: str = ""
    jira_acceptance_criteria: str = ""
    jira_type: str = ""
    jira_priority: str = ""
    jira_images: list[JiraImage] = []

    sf_org_edition: str = ""
    lsc_modules: list[str] = []
    installed_packages: list[str] = []
    metadata_objects: list[str] = []
    metadata_fields: list[str] = []
    metadata_flows: list[str] = []
    metadata_apex_classes: list[str] = []
    metadata_permission_sets: list[str] = []
    # Assignable profiles in the org, used to populate the enablement selector.
    metadata_profiles: list[str] = []

    # How new access (fields, objects, tabs, apps) should be enabled. The
    # reviewer chooses the mechanism up front and the specific targets, so the
    # planner grants access the way this org manages permissions instead of
    # guessing. ``enablement_target`` is "profile" or "permission_set" (or "" if
    # unspecified). Only the matching list is populated.
    enablement_target: str = ""
    enablement_profiles: list[str] = []
    enablement_permission_sets: list[str] = []

    # Existing Layout XML keyed by full name (e.g. "Account-Account Layout"),
    # retrieved from the org so the planner can modify the REAL layout rather
    # than emitting a manual step or clobbering existing sections/fields.
    existing_layouts: dict[str, str] = {}

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
    approved_at: datetime | None = None
    approved_by_id: int | None = None
    deploy_connection_id: int | None = None
    deploy_async_id: str | None = None
    deploy_started_at: datetime | None = None
    deploy_finished_at: datetime | None = None
    deploy_result: dict | None = None
    generation_error: str | None = None

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


class RefinePlanRequest(BaseModel):
    """Human-in-the-loop refinement: revise the same plan from feedback.

    The AI regenerates a refined version of the current plan incorporating
    ``feedback``. Repeatable until the reviewer approves.
    """

    feedback: str


class DeployPlanRequest(BaseModel):
    """Deploy an approved plan to a connected Salesforce org.

    ``check_only`` runs a validation-only deploy (nothing is committed) as a dry
    run before the real deployment.

    ``step_numbers`` and ``artifact_paths`` let the reviewer deploy a SUBSET of
    the plan chosen in the UI at deploy time (selection is not persisted). When
    omitted (None), everything deployable is included. ``step_numbers`` filters
    which steps contribute; ``artifact_paths`` further restricts to specific
    files within those steps. An empty list means "nothing selected".
    """

    salesforce_connection_id: int
    check_only: bool = False
    step_numbers: list[int] | None = None
    artifact_paths: list[str] | None = None


class CommitToGithubRequest(BaseModel):
    """Commit an approved plan's metadata to a branch in a connected repo.

    ``metadata_format`` ("sfdx" | "mdapi") overrides the connection's configured
    format for this commit; when omitted it falls back to the connection setting
    and then to repo auto-detection. ``branch`` defaults to a plan-derived name.
    """

    github_connection_id: int
    repo: str | None = None  # owner/repo override
    branch: str | None = None
    base_branch: str | None = None
    metadata_format: str | None = None  # "sfdx" | "mdapi"
    commit_message: str | None = None


class GithubCommitOut(BaseModel):
    """Result of committing plan artifacts to a GitHub branch."""

    branch: str
    commit_sha: str
    commit_url: str
    branch_url: str
    files: list[str]
    created_branch: bool
    metadata_format: str


class PostTestPlanToJiraRequest(BaseModel):
    """Post the plan's unit test plan as a comment on the story.

    ``jira_connection_id`` selects the JIRA connection to comment through.
    ``ticket_id`` overrides the plan's ticket if needed (defaults to the plan's).
    """

    jira_connection_id: int
    ticket_id: str | None = None


class JiraCommentOut(BaseModel):
    """Result of adding a comment to a JIRA issue."""

    ticket_id: str
    comment_id: str | None = None
    url: str


class ReviewAgainstChecklistRequest(BaseModel):
    """Review the plan against a checklist connection's rubric.

    ``checklist_connection_id`` selects the checklist (a connection of type
    ``checklist``) whose items the plan is evaluated against.
    """

    checklist_connection_id: int


class ChecklistItemResult(BaseModel):
    item: str
    status: str  # "pass" | "fail" | "partial" | "not_applicable"
    finding: str


class ReviewAgainstChecklistOut(BaseModel):
    """Structured compliance review of a plan against a checklist."""

    checklist_name: str
    overall: str  # "pass" | "fail" | "partial"
    summary: str
    results: list[ChecklistItemResult]
