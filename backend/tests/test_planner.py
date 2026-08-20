"""Tests for the planning engine: generation, extraction, retry."""

import json

import pytest

from app.llm.base import LLMProvider, LLMResult
from app.schemas.planning import PlanningContext
from app.services.planner import (
    PlanGenerationError,
    _extract_json,
    generate_plan,
    refine_plan,
)


class ScriptedProvider(LLMProvider):
    """Returns queued responses in order; records prompts received."""

    name = "scripted"

    def __init__(self, responses: list[str]):
        self._responses = responses
        self.calls: list[str] = []
        self.max_tokens_calls: list[int] = []
        self._model = "scripted-model"

    async def complete(self, system_prompt, user_prompt, **kwargs) -> LLMResult:
        self.calls.append(user_prompt)
        self.max_tokens_calls.append(kwargs.get("max_tokens"))
        text = self._responses.pop(0)
        return LLMResult(text=text, model=self._model, provider=self.name)

    async def embed(self, texts):
        raise NotImplementedError


def _ctx() -> PlanningContext:
    return PlanningContext(
        jira_ticket_id="LSC-1",
        jira_summary="Add currency field",
        jira_description="desc",
        jira_acceptance_criteria="ac",
    )


def test_extract_json_from_code_fence():
    raw = "```json\n{\"a\": 1}\n```"
    assert _extract_json(raw) == {"a": 1}


def test_extract_json_with_surrounding_prose():
    raw = "Here is the plan: {\"a\": 1} thanks"
    assert _extract_json(raw) == {"a": 1}


@pytest.mark.asyncio
async def test_generate_plan_succeeds_first_try(valid_plan_dict):
    provider = ScriptedProvider([json.dumps(valid_plan_dict)])
    plan, plan_dict = await generate_plan(provider, _ctx(), max_retries=2)
    assert plan.jira_ticket == "LSC-1"
    assert plan_dict["deployment_risk"] == "Low"
    assert len(provider.calls) == 1
    # Plans are large; the generator must request the configured output budget
    # (not the small default) to avoid mid-JSON truncation.
    from app.core.config import settings

    assert provider.max_tokens_calls[0] == settings.PLAN_MAX_OUTPUT_TOKENS
    assert settings.PLAN_MAX_OUTPUT_TOKENS >= 16000


@pytest.mark.asyncio
async def test_generate_plan_retries_then_succeeds(valid_plan_dict):
    # First response missing a Test step -> business-rule failure; second is valid.
    broken = json.loads(json.dumps(valid_plan_dict))
    broken["steps"] = [s for s in broken["steps"] if s["type"] != "Test"]
    broken["deployment_sequence"]["org_steps"] = [1]
    provider = ScriptedProvider([json.dumps(broken), json.dumps(valid_plan_dict)])

    plan, _ = await generate_plan(provider, _ctx(), max_retries=2)
    assert plan.jira_ticket == "LSC-1"
    assert len(provider.calls) == 2
    # The retry prompt should include the rejection feedback.
    assert "rejected" in provider.calls[1]


@pytest.mark.asyncio
async def test_generate_plan_raises_after_exhausting_retries():
    provider = ScriptedProvider(["not json", "still not json"])
    with pytest.raises(PlanGenerationError) as exc:
        await generate_plan(provider, _ctx(), max_retries=1)
    assert exc.value.attempts == 2
    assert exc.value.last_errors


@pytest.mark.asyncio
async def test_refine_plan_seeds_current_plan_and_feedback(valid_plan_dict):
    import copy

    revised = copy.deepcopy(valid_plan_dict)
    revised["summary"] = "Revised summary"
    provider = ScriptedProvider([json.dumps(revised)])

    plan, plan_dict = await refine_plan(
        provider,
        _ctx(),
        current_plan=valid_plan_dict,
        feedback="Only add the field, drop everything else.",
        max_retries=1,
    )
    assert plan_dict["summary"] == "Revised summary"
    # The single prompt must carry both the current plan and the feedback.
    prompt = provider.calls[0]
    assert "CURRENT PLAN JSON" in prompt
    assert "Only add the field" in prompt


@pytest.mark.asyncio
async def test_refine_prompt_includes_deploy_error_guidance(valid_plan_dict):
    import copy

    revised = copy.deepcopy(valid_plan_dict)
    provider = ScriptedProvider([json.dumps(revised)])

    feedback = (
        "The Salesforce deployment failed with the following errors:\n"
        "- lwc/foo/foo.js: Invalid field Account.Bogus__c"
    )
    await refine_plan(
        provider,
        _ctx(),
        current_plan=valid_plan_dict,
        feedback=feedback,
        max_retries=1,
    )
    prompt = provider.calls[0]
    # The refine prompt must instruct the model to treat deploy errors as
    # authoritative and never invent fields absent from the org context.
    assert "DEPLOYMENT ERRORS" in prompt
    assert "NEVER invent" in prompt
    # The concrete error text must be carried through to the model.
    assert "Account.Bogus__c" in prompt


@pytest.mark.asyncio
async def test_refine_plan_retries_on_invalid_then_succeeds(valid_plan_dict):
    broken = json.loads(json.dumps(valid_plan_dict))
    broken["steps"] = [s for s in broken["steps"] if s["type"] != "Test"]
    broken["deployment_sequence"]["org_steps"] = [1]
    provider = ScriptedProvider([json.dumps(broken), json.dumps(valid_plan_dict)])

    plan, _ = await refine_plan(
        provider,
        _ctx(),
        current_plan=valid_plan_dict,
        feedback="tweak",
        max_retries=2,
    )
    assert plan.jira_ticket == "LSC-1"
    assert len(provider.calls) == 2
    assert "rejected" in provider.calls[1]
