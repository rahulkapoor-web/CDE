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
Environment = Literal["Sandbox", "Production", "Both", "GitHub"]
AutomationFeasibility = Literal["Full", "Partial", "Manual"]

# Step types generally considered destructive / high-risk requiring rollback.
DESTRUCTIVE_TYPES = {"DataMigration", "Deploy", "Apex", "Flow"}


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


class PlanStep(BaseModel):
    step_number: int
    title: str
    type: StepType
    environment: Environment
    description: str
    lsc_guide_reference: str | None = None
    metadata_path: str | None = None
    metadata_artifact: MetadataArtifact | None = None
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
    sandbox_steps: list[int] = Field(default_factory=list)
    production_steps: list[int] = Field(default_factory=list)
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

    # High-risk / destructive steps require a non-empty rollback.
    for s in plan.steps:
        risky = s.type in DESTRUCTIVE_TYPES or s.environment in ("Production", "Both")
        if risky and not (s.rollback and s.rollback.strip()):
            errors.append(
                f"Step {s.step_number} ({s.type}) is high-risk and requires a "
                "non-empty rollback."
            )

    # Every production step must have a corresponding sandbox step.
    prod = set(plan.deployment_sequence.production_steps)
    sandbox = set(plan.deployment_sequence.sandbox_steps)
    if prod and not sandbox:
        errors.append(
            "Production steps present but no sandbox steps in deployment_sequence."
        )
    # Deployment sequence must reference real steps.
    for label, seq in (
        ("sandbox_steps", plan.deployment_sequence.sandbox_steps),
        ("production_steps", plan.deployment_sequence.production_steps),
        ("github_actions_steps", plan.deployment_sequence.github_actions_steps),
    ):
        for n in seq:
            if n not in num_set:
                errors.append(f"deployment_sequence.{label} references unknown step {n}.")

    return errors
