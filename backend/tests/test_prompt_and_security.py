"""Tests for prompt assembly, secret encryption, and SFDX parsing."""

from pathlib import Path

from app.core.security import decrypt_secret, encrypt_secret
from app.connectors.sfdx import parse_sfdx_project
from app.schemas.planning import PlanningContext
from app.services.prompt import build_user_prompt, load_system_prompt


def test_system_prompt_loads():
    text = load_system_prompt()
    assert "ONA" in text
    assert "OUTPUT FORMAT" in text


def test_user_prompt_injects_context():
    ctx = PlanningContext(
        jira_ticket_id="LSC-42",
        jira_summary="Top opportunities widget",
        lsc_modules=["Intelligent Sales"],
        metadata_objects=["Account", "AccountPlan"],
    )
    prompt = build_user_prompt(ctx)
    assert "LSC-42" in prompt
    assert "Top opportunities widget" in prompt
    assert "Intelligent Sales" in prompt
    assert "AccountPlan" in prompt
    assert 'ONA-LSC-42-' in prompt


def test_user_prompt_notes_missing_guide_context():
    prompt = build_user_prompt(PlanningContext(jira_ticket_id="X"))
    assert "No LSC guide excerpts" in prompt


def test_user_prompt_includes_guide_context_when_present():
    prompt = build_user_prompt(
        PlanningContext(jira_ticket_id="X"), guide_context="SECTION 3.2 details"
    )
    assert "SECTION 3.2 details" in prompt


def test_secret_roundtrip():
    plaintext = "super-secret-token"
    enc = encrypt_secret(plaintext)
    assert enc != plaintext
    assert decrypt_secret(enc) == plaintext


def test_sfdx_parser(tmp_path: Path):
    base = tmp_path / "force-app" / "main" / "default"
    (base / "objects" / "Account" / "fields").mkdir(parents=True)
    (base / "objects" / "Account" / "fields" / "ACV__c.field-meta.xml").write_text("<x/>")
    (base / "flows").mkdir(parents=True)
    (base / "flows" / "MyFlow.flow-meta.xml").write_text("<x/>")
    (base / "classes").mkdir(parents=True)
    (base / "classes" / "MyClass.cls").write_text("public class MyClass {}")
    (base / "permissionsets").mkdir(parents=True)
    (base / "permissionsets" / "MyPerm.permissionset-meta.xml").write_text("<x/>")

    result = parse_sfdx_project(str(tmp_path))
    assert "Account" in result["metadata_objects"]
    assert "Account.ACV__c" in result["metadata_fields"]
    assert "MyFlow" in result["metadata_flows"]
    assert "MyClass" in result["metadata_apex_classes"]
    assert "MyPerm" in result["metadata_permission_sets"]
