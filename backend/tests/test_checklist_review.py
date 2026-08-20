"""Tests for reviewing a plan against a checklist (parsing + LLM orchestration).

The LLM is faked so no network is used. We verify item parsing, JSON handling,
overall-verdict derivation, and graceful fallback on bad model output.
"""

import pytest

from app.llm.base import LLMResult
from app.services.checklist_review import (
    parse_checklist_items,
    review_plan_against_checklist,
)


class _FakeProvider:
    name = "fake"

    def __init__(self, text: str = "", raise_exc: Exception | None = None):
        self._text = text
        self._raise = raise_exc
        self.last_user_prompt: str | None = None

    async def complete(self, system_prompt, user_prompt, **kwargs):
        self.last_user_prompt = user_prompt
        if self._raise:
            raise self._raise
        return LLMResult(text=self._text, model="m", provider=self.name)

    async def embed(self, texts):
        return [[0.0] for _ in texts]


def test_parse_checklist_items_strips_markers():
    text = (
        "- All fields have FLS\n"
        "* No hardcoded IDs\n"
        "1. Apex >= 75%\n"
        "2) Layout preserves required fields\n"
        "[ ] Doc updated\n"
        "[x] Reviewed\n"
        "\n"
        "   \n"
        "Plain line"
    )
    items = parse_checklist_items(text)
    assert items == [
        "All fields have FLS",
        "No hardcoded IDs",
        "Apex >= 75%",
        "Layout preserves required fields",
        "Doc updated",
        "Reviewed",
        "Plain line",
    ]


def test_parse_checklist_items_empty():
    assert parse_checklist_items("") == []
    assert parse_checklist_items("\n  \n") == []


@pytest.mark.asyncio
async def test_review_returns_structured_results():
    model_json = (
        '{"overall":"fail","summary":"Missing FLS.",'
        '"results":['
        '{"item":"All fields have FLS","status":"fail","finding":"step 1 omits FLS"},'
        '{"item":"No hardcoded IDs","status":"pass","finding":"none found"}'
        "]}"
    )
    provider = _FakeProvider(text=model_json)
    review = await review_plan_against_checklist(
        provider, {"steps": []}, "- All fields have FLS\n- No hardcoded IDs"
    )
    assert review["overall"] == "fail"
    assert len(review["results"]) == 2
    assert review["results"][0]["status"] == "fail"
    # Checklist items are included in the prompt.
    assert "All fields have FLS" in provider.last_user_prompt


@pytest.mark.asyncio
async def test_review_handles_json_in_code_fence():
    fenced = (
        "Here you go:\n```json\n"
        '{"overall":"pass","summary":"ok","results":'
        '[{"item":"x","status":"pass","finding":"y"}]}'
        "\n```"
    )
    provider = _FakeProvider(text=fenced)
    review = await review_plan_against_checklist(provider, {}, "- x")
    assert review["overall"] == "pass"
    assert review["results"][0]["item"] == "x"


@pytest.mark.asyncio
async def test_review_derives_overall_when_missing():
    # Model omits overall; we derive it from item statuses (partial present).
    model_json = (
        '{"summary":"mixed","results":['
        '{"item":"a","status":"pass","finding":""},'
        '{"item":"b","status":"partial","finding":"half"}'
        "]}"
    )
    provider = _FakeProvider(text=model_json)
    review = await review_plan_against_checklist(provider, {}, "- a\n- b")
    assert review["overall"] == "partial"


@pytest.mark.asyncio
async def test_review_fallback_on_bad_json():
    provider = _FakeProvider(text="not json at all")
    review = await review_plan_against_checklist(provider, {}, "- a\n- b")
    assert review["overall"] == "partial"
    # Items are preserved as not-evaluated so the UI still shows them.
    assert {r["item"] for r in review["results"]} == {"a", "b"}
    assert all(r["status"] == "not_applicable" for r in review["results"])


@pytest.mark.asyncio
async def test_review_fallback_on_llm_exception():
    provider = _FakeProvider(raise_exc=RuntimeError("boom"))
    review = await review_plan_against_checklist(provider, {}, "- a")
    assert review["overall"] == "partial"
    assert "boom" in review["summary"]


@pytest.mark.asyncio
async def test_review_empty_checklist():
    provider = _FakeProvider(text="{}")
    review = await review_plan_against_checklist(provider, {}, "   ")
    assert review["results"] == []
    assert review["overall"] == "partial"
