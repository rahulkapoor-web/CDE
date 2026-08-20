"""Canonical plan contract as Pydantic models plus business-rule validation.

These models mirror the JSON schema in `app/schemas/plan_schema.py`. The LLM must
return JSON that parses into `Plan`. `validate_business_rules` enforces the
additional invariants from the spec that a JSON schema alone cannot express.
"""

from typing import Literal

from pydantic import BaseModel, Field

ChangeClassification = Literal["Configuration", "Customisation", "Mixed"]
DeploymentRisk = Literal["Low", "Medium", "High"]
StepType = Literal[
    "Configuration",
    "Apex",
    "LWC",
    "Flow",
    "PermissionSet",
    "IntegrationSetup",
    "DataMigration",
    "Test",
    "Deploy",
]
# Development happens in the connected (Dev) org; promotion to downstream orgs
# up to production is handled by the external CI/CD pipeline, not this planner.
# A step therefore either runs against the connected org, or is a commit that
# feeds the CI/CD pipeline (GitHub).
Environment = Literal["Org", "GitHub"]
AutomationFeasibility = Literal["Full", "Partial", "Manual"]

# Step types generally considered destructive / high-risk requiring rollback.
DESTRUCTIVE_TYPES = {"DataMigration", "Deploy", "Apex", "Flow"}

# Read-only step types that never mutate an org and so cannot have a meaningful
# rollback (e.g. running a test suite).
NON_DESTRUCTIVE_TYPES = {"Test"}


class LscGuideReference(BaseModel):
    module: str
    section: str
    page_or_url: str
    relevance: str


class MetadataFile(BaseModel):
    """A single file to place in a Metadata API deployment package.

    ``path`` is relative to the package root in classic Metadata API (MDAPI)
    format, e.g. ``objects/HealthCondition.object`` or
    ``layouts/HealthCondition-Health Condition Layout.layout``. ``body`` is the
    file's full XML content.
    """

    path: str
    body: str


class MetadataMember(BaseModel):
    """One ``<types>`` entry for the generated package.xml.

    ``type`` is the Metadata API type name (e.g. ``CustomField``,
    ``CustomObject``, ``Layout``, ``PermissionSet``, ``FlexiPage``) and
    ``name`` is the fullName member (e.g. ``HealthCondition.Diagnosis_Code__c``).
    """

    type: str
    name: str


class MetadataArtifact(BaseModel):
    """Deployable metadata attached to a step.

    Present only on steps that can be applied via the Metadata API. When absent,
    the step is manual (e.g. an out-of-box enablement toggle) and is executed by
    a human following the described clicks. The deployer merges the ``files`` and
    ``members`` of every step's artifact into one package and deploys it.
    """

    files: list[MetadataFile] = Field(default_factory=list)
    members: list[MetadataMember] = Field(default_factory=list)
    api_version: str | None = None


class LayoutFieldEdit(BaseModel):
    """One field to place on a page layout, declaratively.

    The system merges these into the REAL existing layout XML (retrieved from the
    org) so required items are preserved and nothing is dropped — the LLM must
    NOT hand-write full layout XML. ``behavior`` is Edit/Required/Readonly.
    """

    field: str  # API name, e.g. "Specialty__c"
    section: str | None = None  # target section label; created if missing
    behavior: str = "Edit"


class LayoutEdit(BaseModel):
    """A declarative page-layout change resolved into a deployable .layout file.

    ``layout_name`` is the Layout fullName (e.g. "Account-Account Layout"). The
    system loads the existing layout, inserts ``add_fields`` into the named
    section (preserving all existing/required items), and emits the complete
    layout as deployable metadata during plan generation.
    """

    layout_name: str
    add_fields: list[LayoutFieldEdit] = Field(default_factory=list)


class PlanStep(BaseModel):
    step_number: int
    title: str
    type: StepType
    environment: Environment
    description: str
    lsc_guide_reference: str | None = None
    metadata_path: str | None = None
    metadata_artifact: MetadataArtifact | None = None
    # Declarative layout changes; resolved into metadata_artifact files by the
    # backend using the org's existing layout XML. Preferred over hand-written
    # Layout XML because it can never drop required items like Name.
    layout_edits: list[LayoutEdit] = Field(default_factory=list)
    acceptance_check: str
    estimated_minutes: int
    automation_feasibility: AutomationFeasibility
    automation_notes: str | None = None
    dependencies: list[int] = Field(default_factory=list)
    rollback: str | None = None


class TestingRequirements(BaseModel):
    unit_tests: str
    functional_tests: str
    regression_areas: str
    minimum_code_coverage: int = 75


class DeploymentSequence(BaseModel):
    # Steps applied directly to the connected (Dev) org, in order.
    org_steps: list[int] = Field(default_factory=list)
    # Steps committed to GitHub to feed the CI/CD pipeline that promotes changes
    # to downstream orgs up to production.
    github_actions_steps: list[int] = Field(default_factory=list)


class Plan(BaseModel):
    plan_id: str
    jira_ticket: str
    summary: str
    change_classification: ChangeClassification
    deployment_risk: DeploymentRisk
    risk_rationale: str
    estimated_effort: str
    lsc_guide_references: list[LscGuideReference] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    # Read-only context: platform state (perms, licenses, existing objects) the
    # plan ASSUMES is already present. These are NOT steps and are never created
    # or deployed — they document the environment the plan is written against.
    assumed_prerequisites: list[str] = Field(default_factory=list)
    steps: list[PlanStep]
    testing_requirements: TestingRequirements
    deployment_sequence: DeploymentSequence
    post_deployment: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    copilot_assist_available: bool = True
    copilot_suggested_actions: list[str] = Field(default_factory=list)


class BusinessRuleError(ValueError):
    """Raised when a parsed plan violates spec business rules."""


def validate_business_rules(plan: Plan) -> list[str]:
    """Return a list of business-rule violation messages (empty == valid)."""
    errors: list[str] = []

    step_numbers = [s.step_number for s in plan.steps]

    # Unique, positive step numbers.
    if len(set(step_numbers)) != len(step_numbers):
        errors.append("Duplicate step_number values found.")

    # At least one Test step.
    if not any(s.type == "Test" for s in plan.steps):
        errors.append("Plan must include at least one step of type 'Test'.")

    # Dependencies must reference valid, earlier steps (acyclic by construction).
    num_set = set(step_numbers)
    for s in plan.steps:
        for dep in s.dependencies:
            if dep not in num_set:
                errors.append(
                    f"Step {s.step_number} depends on unknown step {dep}."
                )
            elif dep >= s.step_number:
                errors.append(
                    f"Step {s.step_number} depends on step {dep} that is not "
                    "earlier (possible cycle)."
                )

    # Destructive steps require a non-empty rollback. Read-only step types
    # (e.g. Test) never mutate the org, so they are exempt.
    for s in plan.steps:
        if s.type in NON_DESTRUCTIVE_TYPES:
            continue
        if s.type in DESTRUCTIVE_TYPES and not (s.rollback and s.rollback.strip()):
            errors.append(
                f"Step {s.step_number} ({s.type}) is high-risk and requires a "
                "non-empty rollback."
            )

    # Deployment sequence must reference real steps.
    for label, seq in (
        ("org_steps", plan.deployment_sequence.org_steps),
        ("github_actions_steps", plan.deployment_sequence.github_actions_steps),
    ):
        for n in seq:
            if n not in num_set:
                errors.append(f"deployment_sequence.{label} references unknown step {n}.")

    return errors
