"""Tests for LLM output coercion into the canonical plan shape.

Each case mirrors a real drift pattern observed in production generation logs.
"""

import jsonschema
import pytest

from app.schemas.plan import Plan
from app.schemas.plan_schema import PLAN_JSON_SCHEMA
from app.services.plan_coercion import coerce_plan_data


def _base_plan() -> dict:
    """A minimal, valid plan used as a baseline for targeted drift injection."""
    return {
        "plan_id": "PLAN-1",
        "jira_ticket": "LSC-42",
        "summary": "Do the thing",
        "change_classification": "Configuration",
        "deployment_risk": "Low",
        "risk_rationale": "Low impact config change.",
        "estimated_effort": "1-2 days",
        "lsc_guide_references": [
            {
                "module": "Care Plans",
                "section": "Setup",
                "page_or_url": "http://x",
                "relevance": "Directly relevant.",
            }
        ],
        "prerequisites": ["Sandbox access"],
        "steps": [
            {
                "step_number": 1,
                "title": "Configure field",
                "type": "Configuration",
                "environment": "Sandbox",
                "description": "Add a field.",
                "acceptance_check": "Field exists.",
                "estimated_minutes": 30,
                "automation_feasibility": "Manual",
                "dependencies": [],
            },
            {
                "step_number": 2,
                "title": "Test it",
                "type": "Test",
                "environment": "Sandbox",
                "description": "Verify.",
                "acceptance_check": "Passes.",
                "estimated_minutes": 15,
                "automation_feasibility": "Manual",
                "dependencies": [1],
            },
        ],
        "testing_requirements": {
            "unit_tests": "n/a",
            "functional_tests": "Manual verification.",
            "regression_areas": "None.",
            "minimum_code_coverage": 75,
        },
        "deployment_sequence": {
            "sandbox_steps": [1, 2],
            "production_steps": [],
            "github_actions_steps": [],
        },
        "post_deployment": ["Smoke test"],
        "open_questions": ["Any SLA?"],
        "copilot_assist_available": True,
        "copilot_suggested_actions": ["Generate the field metadata"],
    }


def _assert_valid(data: dict) -> Plan:
    """Coerce then assert the result passes both validators."""
    coerced = coerce_plan_data(data)
    jsonschema.validate(coerced, PLAN_JSON_SCHEMA)
    return Plan.model_validate(coerced)


def test_valid_plan_passes_through_unchanged():
    data = _base_plan()
    plan = _assert_valid(data)
    assert plan.testing_requirements.minimum_code_coverage == 75


def test_testing_requirements_as_string_is_wrapped():
    data = _base_plan()
    data["testing_requirements"] = (
        "All 11 test scenarios must pass before production deployment."
    )
    plan = _assert_valid(data)
    assert "11 test scenarios" in plan.testing_requirements.functional_tests
    assert plan.testing_requirements.minimum_code_coverage == 75


def test_testing_requirements_extra_keys_folded_and_coverage_alias():
    data = _base_plan()
    data["testing_requirements"] = {
        "unit_tests": "Apex tests.",
        "functional_tests": "UI flows.",
        "regression_scope": "Account automation.",
        "minimum_apex_coverage_percent": 80,
        "evidence_required": True,
        "notes": "Attach screenshots.",
    }
    plan = _assert_valid(data)
    tr = plan.testing_requirements
    assert tr.minimum_code_coverage == 80
    # regression_scope alias maps to regression_areas.
    assert "Account automation" in tr.regression_areas
    # Unknown keys are preserved by folding into regression_areas.
    assert "evidence_required" in tr.regression_areas
    assert "notes" in tr.regression_areas


def test_deployment_sequence_as_string_falls_back_to_sandbox():
    data = _base_plan()
    data["deployment_sequence"] = "Deploy to sandbox, validate, then production."
    plan = _assert_valid(data)
    assert plan.deployment_sequence.sandbox_steps == [1, 2]
    assert plan.deployment_sequence.production_steps == []


def test_deployment_sequence_string_step_numbers_coerced_to_int():
    data = _base_plan()
    data["deployment_sequence"] = {
        "sandbox_steps": ["1", "2"],
        "production_steps": [],
        "github_actions_steps": [],
    }
    plan = _assert_valid(data)
    assert plan.deployment_sequence.sandbox_steps == [1, 2]


def test_open_questions_as_objects_flattened_to_strings():
    data = _base_plan()
    data["open_questions"] = [
        {"question": "What is the SLA?"},
        {"text": "Who approves?"},
        {"topic": "budget", "detail": "confirm cap"},
    ]
    plan = _assert_valid(data)
    assert plan.open_questions[0] == "What is the SLA?"
    assert plan.open_questions[1] == "Who approves?"
    assert "budget" in plan.open_questions[2]


def test_lsc_guide_references_as_strings_wrapped_to_objects():
    data = _base_plan()
    data["lsc_guide_references"] = ["Care Plans module", "Consent management"]
    plan = _assert_valid(data)
    assert plan.lsc_guide_references[0].module == "Care Plans module"
    assert plan.lsc_guide_references[0].section == ""


def test_lsc_guide_references_dict_missing_keys_filled():
    data = _base_plan()
    data["lsc_guide_references"] = [
        {"module": "Care Plans"},  # missing section/page_or_url/relevance
        {"name": "Consent", "url": "http://y", "why": "consent rules"},  # aliases
    ]
    plan = _assert_valid(data)
    assert plan.lsc_guide_references[0].module == "Care Plans"
    assert plan.lsc_guide_references[0].section == ""
    assert plan.lsc_guide_references[1].module == "Consent"
    assert plan.lsc_guide_references[1].page_or_url == "http://y"
    assert plan.lsc_guide_references[1].relevance == "consent rules"


def test_step_dependencies_string_ints_coerced():
    data = _base_plan()
    data["steps"][1]["dependencies"] = ["1"]
    plan = _assert_valid(data)
    assert plan.steps[1].dependencies == [1]


def test_prerequisites_and_post_deployment_objects_flattened():
    data = _base_plan()
    data["prerequisites"] = [{"item": "Sandbox access"}]
    data["post_deployment"] = [{"text": "Run smoke test"}]
    plan = _assert_valid(data)
    assert plan.prerequisites == ["Sandbox access"]
    assert plan.post_deployment == ["Run smoke test"]


def test_non_dict_input_returned_unchanged():
    assert coerce_plan_data("not a dict") == "not a dict"
    assert coerce_plan_data([1, 2, 3]) == [1, 2, 3]


def test_combined_drift_all_patterns_at_once():
    """The exact combination seen failing repeatedly in the logs."""
    data = _base_plan()
    data["testing_requirements"] = "Everything must pass before prod."
    data["deployment_sequence"] = "sandbox then prod"
    data["open_questions"] = [{"question": "Q1"}, {"question": "Q2"}]
    data["lsc_guide_references"] = ["Module A", "Module B"]
    plan = _assert_valid(data)
    assert plan.testing_requirements.minimum_code_coverage == 75
    assert plan.deployment_sequence.sandbox_steps == [1, 2]
    assert plan.open_questions == ["Q1", "Q2"]
    assert plan.lsc_guide_references[0].module == "Module A"
