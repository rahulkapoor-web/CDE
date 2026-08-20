"""Planning engine: generation with strict schema validation and auto-retry."""

import json
import logging
import re

import jsonschema
from pydantic import ValidationError

from app.core.config import settings
from app.llm.base import ImageInput, LLMProvider
from app.schemas.plan import Plan, validate_business_rules
from app.schemas.plan_schema import PLAN_JSON_SCHEMA
from app.schemas.planning import PlanningContext
from app.services.plan_coercion import coerce_plan_data
from app.services.prompt import build_user_prompt, load_system_prompt

logger = logging.getLogger(__name__)


class PlanGenerationError(Exception):
    def __init__(self, message: str, attempts: int, last_errors: list[str]):
        super().__init__(message)
        self.attempts = attempts
        self.last_errors = last_errors


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1)
    # If extra prose surrounds the object, grab the outermost braces.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
    return json.loads(text)


def _validate(raw: str) -> tuple[Plan | None, list[str]]:
    """Validate raw LLM text. Returns (plan, errors)."""
    errors: list[str] = []
    try:
        data = _extract_json(raw)
    except json.JSONDecodeError as exc:
        return None, [f"Response was not valid JSON: {exc}"]

    # Normalize known LLM shape drift before strict validation.
    data = coerce_plan_data(data)

    try:
        jsonschema.validate(data, PLAN_JSON_SCHEMA)
    except jsonschema.ValidationError as exc:
        path = "/".join(str(p) for p in exc.path)
        errors.append(f"Schema error at '{path or '<root>'}': {exc.message}")

    plan: Plan | None = None
    try:
        plan = Plan.model_validate(data)
    except ValidationError as exc:
        for e in exc.errors():
            loc = "/".join(str(p) for p in e["loc"])
            errors.append(f"Model error at '{loc}': {e['msg']}")

    if plan is not None:
        errors.extend(validate_business_rules(plan))

    if errors:
        return None, errors
    return plan, []


async def generate_plan(
    provider: LLMProvider,
    context: PlanningContext,
    guide_context: str = "",
    max_retries: int | None = None,
    images: list[ImageInput] | None = None,
) -> tuple[Plan, dict]:
    """Generate and validate a plan. Retries on invalid output.

    ``images`` are optional design exports (e.g. a Figma frame) passed to the
    provider as visual context on every attempt.

    Returns (plan, plan_dict). Raises PlanGenerationError on persistent failure.
    """
    max_retries = settings.PLAN_MAX_RETRIES if max_retries is None else max_retries
    system_prompt = load_system_prompt()
    user_prompt = build_user_prompt(context, guide_context, has_images=bool(images))

    last_errors: list[str] = []
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        prompt = user_prompt
        if last_errors:
            prompt = (
                user_prompt
                + "\n\nYour previous response was rejected for these reasons:\n"
                + "\n".join(f"- {e}" for e in last_errors)
                + "\n\nReturn a corrected JSON object that fixes all issues."
            )
        result = await provider.complete(
            system_prompt,
            prompt,
            images=images,
            max_tokens=settings.PLAN_MAX_OUTPUT_TOKENS,
        )
        plan, errors = _validate(result.text)
        if plan is not None:
            return plan, plan.model_dump()
        last_errors = errors
        logger.warning("Plan validation failed (attempt %d): %s", attempts, errors)

    raise PlanGenerationError(
        "LLM output failed schema/business-rule validation after retries.",
        attempts=attempts,
        last_errors=last_errors,
    )


def _build_refine_prompt(
    context: PlanningContext,
    current_plan: dict,
    feedback: str,
    guide_context: str,
    has_images: bool,
) -> str:
    """Prompt the model to revise an existing plan given reviewer feedback.

    The original context is included so the model keeps grounding, the current
    plan JSON is the starting point, and the feedback is the change request.
    """
    base = build_user_prompt(context, guide_context, has_images=has_images)
    current_json = json.dumps(current_plan, indent=2, ensure_ascii=False)
    return (
        base
        + "\n\nREVISION TASK\n"
        + "A reviewer has an EXISTING plan (below) and wants it revised. Apply "
        "the reviewer's feedback to that plan and return the FULL revised plan "
        "as a single JSON object conforming to the same schema. Preserve every "
        "part the feedback does not ask to change (keep plan_id and jira_ticket "
        "identical). Honour SCOPE DISCIPLINE: change only what the feedback and "
        "the original story require.\n\n"
        "IF THE FEEDBACK CONTAINS DEPLOYMENT ERRORS: the plan was already "
        "deployed and Salesforce rejected specific components. Treat each error "
        "as authoritative and fix the exact component it names — do not rewrite "
        "unrelated steps. Common fixes: correct an invalid field/object/apex "
        "reference to one that actually exists in the Org Metadata Snapshot "
        "above; ensure an LWC bundle includes ALL required files (.html, .js, "
        "and .js-meta.xml with valid apiVersion/targets); ensure a FlexiPage or "
        "layout only references components/fields that exist; fix malformed XML; "
        "and correct step dependency ordering. NEVER invent a field, object, or "
        "component that is not present in the org context — if a referenced "
        "field does not exist, either add an explicit earlier step to create it "
        "(with its metadata_artifact) or remove the reference.\n\n"
        "CURRENT PLAN JSON:\n"
        + current_json
        + "\n\nREVIEWER FEEDBACK:\n"
        + feedback.strip()
        + "\n\nReturn ONLY the revised JSON object, no surrounding text."
    )


async def refine_plan(
    provider: LLMProvider,
    context: PlanningContext,
    current_plan: dict,
    feedback: str,
    guide_context: str = "",
    max_retries: int | None = None,
    images: list[ImageInput] | None = None,
) -> tuple[Plan, dict]:
    """Revise an existing plan from reviewer feedback, keeping it schema-valid.

    Mirrors :func:`generate_plan`'s validate/auto-retry loop but seeds the model
    with the current plan and the feedback. Returns (plan, plan_dict); raises
    PlanGenerationError on persistent invalid output.
    """
    max_retries = settings.PLAN_MAX_RETRIES if max_retries is None else max_retries
    system_prompt = load_system_prompt()
    refine_prompt = _build_refine_prompt(
        context, current_plan, feedback, guide_context, has_images=bool(images)
    )

    last_errors: list[str] = []
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        prompt = refine_prompt
        if last_errors:
            prompt = (
                refine_prompt
                + "\n\nYour previous response was rejected for these reasons:\n"
                + "\n".join(f"- {e}" for e in last_errors)
                + "\n\nReturn a corrected JSON object that fixes all issues."
            )
        result = await provider.complete(
            system_prompt,
            prompt,
            images=images,
            max_tokens=settings.PLAN_MAX_OUTPUT_TOKENS,
        )
        plan, errors = _validate(result.text)
        if plan is not None:
            return plan, plan.model_dump()
        last_errors = errors
        logger.warning("Plan refine failed (attempt %d): %s", attempts, errors)

    raise PlanGenerationError(
        "Refined LLM output failed schema/business-rule validation after retries.",
        attempts=attempts,
        last_errors=last_errors,
    )
