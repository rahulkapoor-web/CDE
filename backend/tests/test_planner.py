"""Tests for the planning engine: generation, extraction, retry."""

import json

import pytest

from app.llm.base import LLMProvider, LLMResult
from app.schemas.planning import PlanningContext
from app.services.planner import PlanGenerationError, _extract_json, generate_plan


class ScriptedProvider(LLMProvider):
    """Returns queued responses in order; records prompts received."""

    name = "scripted"

    def __init__(self, responses: list[str]):
        self._responses = responses
        self.calls: list[str] = []
        self._model = "scripted-model"

    async def complete(self, system_prompt, user_prompt, **kwargs) -> LLMResult:
        self.calls.append(user_prompt)
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


@pytest.mark.asyncio
async def test_generate_plan_retries_then_succeeds(valid_plan_dict):
    # First response missing a Test step -> business-rule failure; second is valid.
    broken = json.loads(json.dumps(valid_plan_dict))
    broken["steps"] = [s for s in broken["steps"] if s["type"] != "Test"]
    broken["deployment_sequence"]["sandbox_steps"] = [1]
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
