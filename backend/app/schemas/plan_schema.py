"""Canonical JSON Schema for the ONA plan output.

Used to validate raw LLM output before parsing into Pydantic models, and exposed
via the API so clients/tests share one source of truth.
"""

PLAN_JSON_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ONAPlan",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "plan_id",
        "jira_ticket",
        "summary",
        "change_classification",
        "deployment_risk",
        "risk_rationale",
        "estimated_effort",
        "lsc_guide_references",
        "prerequisites",
        "assumed_prerequisites",
        "steps",
        "testing_requirements",
        "deployment_sequence",
        "post_deployment",
        "open_questions",
        "copilot_assist_available",
        "copilot_suggested_actions",
    ],
    "properties": {
        "plan_id": {"type": "string"},
        "jira_ticket": {"type": "string"},
        "summary": {"type": "string"},
        "change_classification": {
            "type": "string",
            "enum": ["Configuration", "Customisation", "Mixed"],
        },
        "deployment_risk": {
            "type": "string",
            "enum": ["Low", "Medium", "High"],
        },
        "risk_rationale": {"type": "string"},
        "estimated_effort": {"type": "string"},
        "lsc_guide_references": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["module", "section", "page_or_url", "relevance"],
                "properties": {
                    "module": {"type": "string"},
                    "section": {"type": "string"},
                    "page_or_url": {"type": "string"},
                    "relevance": {"type": "string"},
                },
            },
        },
        "prerequisites": {"type": "array", "items": {"type": "string"}},
        "assumed_prerequisites": {"type": "array", "items": {"type": "string"}},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "step_number",
                    "title",
                    "type",
                    "environment",
                    "description",
                    "acceptance_check",
                    "estimated_minutes",
                    "automation_feasibility",
                    "dependencies",
                ],
                "properties": {
                    "step_number": {"type": "integer", "minimum": 1},
                    "title": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "Configuration",
                            "Apex",
                            "LWC",
                            "Flow",
                            "PermissionSet",
                            "IntegrationSetup",
                            "DataMigration",
                            "Test",
                            "Deploy",
                        ],
                    },
                    "environment": {
                        "type": "string",
                        "enum": ["Org", "GitHub"],
                    },
                    "description": {"type": "string"},
                    "lsc_guide_reference": {"type": ["string", "null"]},
                    "metadata_path": {"type": ["string", "null"]},
                    "metadata_artifact": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["path", "body"],
                                    "properties": {
                                        "path": {"type": "string"},
                                        "body": {"type": "string"},
                                    },
                                },
                            },
                            "members": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["type", "name"],
                                    "properties": {
                                        "type": {"type": "string"},
                                        "name": {"type": "string"},
                                    },
                                },
                            },
                            "api_version": {"type": ["string", "null"]},
                        },
                    },
                    "layout_edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["layout_name", "add_fields"],
                            "properties": {
                                "layout_name": {"type": "string"},
                                "add_fields": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["field"],
                                        "properties": {
                                            "field": {"type": "string"},
                                            "section": {
                                                "type": ["string", "null"]
                                            },
                                            "behavior": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "acceptance_check": {"type": "string"},
                    "estimated_minutes": {"type": "integer", "minimum": 0},
                    "automation_feasibility": {
                        "type": "string",
                        "enum": ["Full", "Partial", "Manual"],
                    },
                    "automation_notes": {"type": ["string", "null"]},
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "rollback": {"type": ["string", "null"]},
                },
            },
        },
        "testing_requirements": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "unit_tests",
                "functional_tests",
                "regression_areas",
                "minimum_code_coverage",
            ],
            "properties": {
                "unit_tests": {"type": "string"},
                "functional_tests": {"type": "string"},
                "regression_areas": {"type": "string"},
                "minimum_code_coverage": {"type": "integer", "minimum": 0, "maximum": 100},
            },
        },
        "deployment_sequence": {
            "type": "object",
            "additionalProperties": False,
            "required": ["org_steps", "github_actions_steps"],
            "properties": {
                "org_steps": {"type": "array", "items": {"type": "integer"}},
                "github_actions_steps": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
        },
        "post_deployment": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "copilot_assist_available": {"type": "boolean"},
        "copilot_suggested_actions": {"type": "array", "items": {"type": "string"}},
    },
}
