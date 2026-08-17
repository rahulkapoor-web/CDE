"""Tests for the Metadata API packaging and deploy/poll logic.

Packaging is pure and tested directly. The deploy call is tested against a fake
Salesforce client so no live org is required.
"""

import copy
import io
import zipfile

import pytest

from app.schemas.plan import Plan
from app.services.deployer import (
    NoDeployableMetadataError,
    build_package_xml,
    build_package_zip,
    deploy_plan,
)


def _plan_with_artifacts(base: dict) -> Plan:
    """Attach deployable artifacts to steps 1 and 2 of the shared plan."""
    data = copy.deepcopy(base)
    data["steps"][0]["metadata_artifact"] = {
        "files": [
            {
                "path": "objects/HealthCondition/fields/Diagnosis_Code__c.field-meta.xml",
                "body": "<CustomField><fullName>Diagnosis_Code__c</fullName></CustomField>",
            }
        ],
        "members": [
            {"type": "CustomField", "name": "HealthCondition.Diagnosis_Code__c"}
        ],
        "api_version": "60.0",
    }
    data["steps"][1]["metadata_artifact"] = {
        "files": [
            {
                "path": "permissionsets/PSL.permissionset-meta.xml",
                "body": "<PermissionSet><label>PSL</label></PermissionSet>",
            }
        ],
        "members": [{"type": "PermissionSet", "name": "PSL"}],
    }
    return Plan.model_validate(data)


def test_build_package_zip_merges_all_steps(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    pkg = build_package_zip(plan)

    assert "objects/HealthCondition/fields/Diagnosis_Code__c.field-meta.xml" in pkg.file_paths
    assert "permissionsets/PSL.permissionset-meta.xml" in pkg.file_paths
    assert pkg.steps_included == [1, 2]

    # The zip contains a generated package.xml plus both source files.
    zf = zipfile.ZipFile(io.BytesIO(pkg.zip_bytes))
    names = set(zf.namelist())
    assert "package.xml" in names
    assert len(names) == 3


def test_package_xml_lists_types_and_members(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    xml = build_package_xml(plan)
    assert "<name>CustomField</name>" in xml
    assert "<members>HealthCondition.Diagnosis_Code__c</members>" in xml
    assert "<name>PermissionSet</name>" in xml
    assert "<members>PSL</members>" in xml
    # api_version from the first artifact that declares one.
    assert "<version>60.0</version>" in xml


def test_build_package_zip_raises_when_no_metadata(valid_plan_dict):
    # The shared plan has no metadata_artifact on any step.
    plan = Plan.model_validate(valid_plan_dict)
    with pytest.raises(NoDeployableMetadataError):
        build_package_zip(plan)


def test_build_package_zip_rejects_conflicting_file_bodies(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    art = {
        "files": [{"path": "objects/X.object", "body": "<A/>"}],
        "members": [{"type": "CustomObject", "name": "X"}],
    }
    data["steps"][0]["metadata_artifact"] = copy.deepcopy(art)
    conflicting = copy.deepcopy(art)
    conflicting["files"][0]["body"] = "<B/>"  # same path, different body
    data["steps"][1]["metadata_artifact"] = conflicting
    plan = Plan.model_validate(data)
    with pytest.raises(ValueError, match="Conflicting content"):
        build_package_zip(plan)


def test_build_package_zip_rejects_user_supplied_package_xml(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["metadata_artifact"] = {
        "files": [{"path": "package.xml", "body": "<Package/>"}],
        "members": [],
    }
    plan = Plan.model_validate(data)
    with pytest.raises(ValueError, match="package.xml"):
        build_package_zip(plan)


class _FakeSF:
    """Minimal stand-in for simple_salesforce.Salesforce for deploy tests."""

    def __init__(self, states: list[str], detail: dict | None = None):
        self._states = states
        self._detail = detail
        self.deploy_kwargs: dict = {}
        self.polls = 0

    def deploy(self, zipfile_obj, sandbox, **kwargs):
        self.deploy_kwargs = {"sandbox": sandbox, **kwargs}
        return ("0Af_ASYNC", "Queued")

    def checkDeployStatus(self, async_id):
        assert async_id == "0Af_ASYNC"
        state = self._states[min(self.polls, len(self._states) - 1)]
        self.polls += 1
        detail = self._detail or {
            "total_count": "2",
            "deployed_count": "2" if state == "Succeeded" else "0",
            "failed_count": "0",
            "errors": [],
        }
        return {
            "state": state,
            "state_detail": None,
            "deployment_detail": detail,
            "unit_test_detail": {"total_count": "0", "failed_count": "0", "errors": []},
        }


def test_deploy_plan_success_polls_to_terminal(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    sf = _FakeSF(states=["InProgress", "InProgress", "Succeeded"])
    async_id, status = deploy_plan(
        sf, plan, is_sandbox=True, poll_interval=0, _sleep=lambda s: None
    )
    assert async_id == "0Af_ASYNC"
    assert status["succeeded"] is True
    assert status["state"] == "Succeeded"
    assert status["package_files"]
    assert sf.polls == 3
    # rollbackOnError should be requested for safety.
    assert sf.deploy_kwargs["rollbackOnError"] is True
    assert sf.deploy_kwargs["sandbox"] is True
    assert sf.deploy_kwargs["checkOnly"] is False


def test_deploy_plan_failure_reports_component_errors(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    detail = {
        "total_count": "2",
        "deployed_count": "1",
        "failed_count": "1",
        "errors": [
            {"file": "objects/X", "message": "bad field", "type": "CustomField"}
        ],
    }
    sf = _FakeSF(states=["Failed"], detail=detail)
    _async_id, status = deploy_plan(
        sf, plan, is_sandbox=False, poll_interval=0, _sleep=lambda s: None
    )
    assert status["succeeded"] is False
    assert status["state"] == "Failed"
    assert status["component_errors"][0]["message"] == "bad field"


def test_deploy_plan_check_only_sets_flag(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    sf = _FakeSF(states=["Succeeded"])
    deploy_plan(
        sf,
        plan,
        is_sandbox=True,
        check_only=True,
        poll_interval=0,
        _sleep=lambda s: None,
    )
    assert sf.deploy_kwargs["checkOnly"] is True


def test_deploy_plan_times_out(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    # Never reaches a terminal state.
    sf = _FakeSF(states=["InProgress"])
    _async_id, status = deploy_plan(
        sf,
        plan,
        is_sandbox=True,
        poll_interval=0,
        timeout=0,  # force immediate timeout on first non-terminal poll
        _sleep=lambda s: None,
    )
    assert status["succeeded"] is False
