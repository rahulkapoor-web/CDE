"""Tests for the plan schema and business-rule validation."""

import jsonschema
import pytest

from app.schemas.plan import Plan, validate_business_rules
from app.schemas.plan_schema import PLAN_JSON_SCHEMA


def test_valid_plan_passes_json_schema(valid_plan_dict):
    jsonschema.validate(valid_plan_dict, PLAN_JSON_SCHEMA)


def test_valid_plan_passes_business_rules(valid_plan_dict):
    plan = Plan.model_validate(valid_plan_dict)
    assert validate_business_rules(plan) == []


def test_missing_test_step_is_flagged(valid_plan_dict):
    valid_plan_dict["steps"] = [
        s for s in valid_plan_dict["steps"] if s["type"] != "Test"
    ]
    # Fix deployment sequence to only reference remaining steps.
    valid_plan_dict["deployment_sequence"]["org_steps"] = [1]
    plan = Plan.model_validate(valid_plan_dict)
    errors = validate_business_rules(plan)
    assert any("at least one step of type 'Test'" in e for e in errors)


def test_high_risk_step_requires_rollback(valid_plan_dict):
    # Remove rollback from the destructive Deploy step.
    for s in valid_plan_dict["steps"]:
        if s["type"] == "Deploy":
            s["rollback"] = None
    plan = Plan.model_validate(valid_plan_dict)
    errors = validate_business_rules(plan)
    assert any("requires a" in e and "rollback" in e for e in errors)


def test_test_step_does_not_require_rollback(valid_plan_dict):
    # A read-only Test step never mutates the org, so it must not be flagged as
    # high-risk (regression: an env-based rule forced Test steps to carry a
    # rollback, making generation fail on every retry).
    for s in valid_plan_dict["steps"]:
        if s["type"] == "Test":
            s["rollback"] = None
    plan = Plan.model_validate(valid_plan_dict)
    errors = validate_business_rules(plan)
    assert not any("requires a" in e and "rollback" in e for e in errors)


def test_forward_dependency_is_flagged(valid_plan_dict):
    valid_plan_dict["steps"][0]["dependencies"] = [3]  # step 1 depends on step 3
    plan = Plan.model_validate(valid_plan_dict)
    errors = validate_business_rules(plan)
    assert any("not " in e and "earlier" in e for e in errors)


def test_unknown_dependency_is_flagged(valid_plan_dict):
    valid_plan_dict["steps"][1]["dependencies"] = [99]
    plan = Plan.model_validate(valid_plan_dict)
    errors = validate_business_rules(plan)
    assert any("unknown step 99" in e for e in errors)


def test_deployment_sequence_unknown_step_flagged(valid_plan_dict):
    valid_plan_dict["deployment_sequence"]["org_steps"] = [42]
    plan = Plan.model_validate(valid_plan_dict)
    errors = validate_business_rules(plan)
    assert any("unknown step 42" in e for e in errors)


def test_invalid_enum_rejected_by_json_schema(valid_plan_dict):
    valid_plan_dict["deployment_risk"] = "Critical"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(valid_plan_dict, PLAN_JSON_SCHEMA)
