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
        result = await provider.complete(system_prompt, prompt, images=images)
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
