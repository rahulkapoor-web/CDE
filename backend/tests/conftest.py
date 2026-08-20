"""Shared test fixtures: a valid plan dict and helper builders."""

import copy

import pytest


@pytest.fixture
def valid_plan_dict() -> dict:
    return copy.deepcopy(_VALID_PLAN)


_VALID_PLAN: dict = {
    "plan_id": "ONA-LSC-1-20260817T000000Z",
    "jira_ticket": "LSC-1",
    "summary": "Add a currency field to Account and surface it on the layout.",
    "change_classification": "Configuration",
    "deployment_risk": "Low",
    "risk_rationale": "Config-only change with no managed package impact.",
    "estimated_effort": "2-3 hours",
    "lsc_guide_references": [
        {
            "module": "Intelligent Sales",
            "section": "Account Plan Setup",
            "page_or_url": "Verify in LSC Configuration Guide: Account Plan",
            "relevance": "Confirms Account Plan layout ownership.",
        }
    ],
    "prerequisites": ["Sandbox refreshed from production."],
    "steps": [
        {
            "step_number": 1,
            "title": "Create currency field on Account",
            "type": "Configuration",
            "environment": "Sandbox",
            "description": "Navigate to Setup → Object Manager → Account → Fields.",
            "lsc_guide_reference": None,
            "metadata_path": "force-app/main/default/objects/Account/fields/ACV__c.field-meta.xml",
            "acceptance_check": "Field visible on Account with correct type.",
            "estimated_minutes": 30,
            "automation_feasibility": "Full",
            "automation_notes": None,
            "dependencies": [],
            "rollback": None,
        },
        {
            "step_number": 2,
            "title": "Write Apex test for field access",
            "type": "Test",
            "environment": "Sandbox",
            "description": "Add a test class verifying the field is queryable.",
            "lsc_guide_reference": None,
            "metadata_path": None,
            "acceptance_check": "Test passes with >75% coverage.",
            "estimated_minutes": 20,
            "automation_feasibility": "Full",
            "automation_notes": None,
            "dependencies": [1],
            "rollback": "Delete the test class via destructiveChanges.",
        },
        {
            "step_number": 3,
            "title": "Deploy to production",
            "type": "Deploy",
            "environment": "Production",
            "description": "Deploy via GitHub Actions after UAT sign-off.",
            "lsc_guide_reference": None,
            "metadata_path": None,
            "acceptance_check": "Deployment succeeds; field present in prod.",
            "estimated_minutes": 15,
            "automation_feasibility": "Full",
            "automation_notes": None,
            "dependencies": [1, 2],
            "rollback": "Roll back via destructiveChanges removing ACV__c.",
        },
    ],
    "testing_requirements": {
        "unit_tests": "AccountFieldTest",
        "functional_tests": "Verify field on layout in UAT.",
        "regression_areas": "Account page layouts.",
        "minimum_code_coverage": 75,
    },
    "deployment_sequence": {
        "sandbox_steps": [1, 2],
        "production_steps": [3],
        "github_actions_steps": [3],
    },
    "post_deployment": ["Set JIRA ticket to Done."],
    "open_questions": [],
    "copilot_assist_available": True,
    "copilot_suggested_actions": ["Generate the Apex test skeleton."],
}
