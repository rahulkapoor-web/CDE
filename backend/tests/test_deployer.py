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
    filter_plan_for_deploy,
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


def _plan_with_apex(base: dict, meta_version: str) -> Plan:
    """Plan whose first step ships an Apex class whose meta declares a version."""
    data = copy.deepcopy(base)
    data["steps"][0]["metadata_artifact"] = {
        "files": [
            {"path": "classes/Foo.cls", "body": "public class Foo {}"},
            {
                "path": "classes/Foo.cls-meta.xml",
                "body": (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
                    f"    <apiVersion>{meta_version}</apiVersion>\n"
                    "    <status>Active</status>\n"
                    "</ApexClass>\n"
                ),
            },
        ],
        "members": [{"type": "ApexClass", "name": "Foo"}],
        "api_version": meta_version,
    }
    return Plan.model_validate(data)


def _read_zip(pkg) -> dict[str, str]:
    zf = zipfile.ZipFile(io.BytesIO(pkg.zip_bytes))
    return {n: zf.read(n).decode() for n in zf.namelist()}


def test_org_api_version_overrides_meta_and_package(valid_plan_dict):
    """The org's API version rewrites the meta file's apiVersion and package.xml
    version, so a stale LLM-authored version never reaches the org."""
    plan = _plan_with_apex(valid_plan_dict, meta_version="55.0")
    pkg = build_package_zip(plan, api_version="62.0")

    files = _read_zip(pkg)
    assert "<version>62.0</version>" in files["package.xml"]
    assert "<version>55.0</version>" not in files["package.xml"]
    meta = files["classes/Foo.cls-meta.xml"]
    assert "<apiVersion>62.0</apiVersion>" in meta
    assert "55.0" not in meta
    # The Apex body itself is untouched.
    assert files["classes/Foo.cls"] == "public class Foo {}"


def test_default_api_version_falls_back_to_artifact(valid_plan_dict):
    """When the caller passes the built-in default (org version unknown), the
    artifact-declared version is used rather than clobbering it."""
    plan = _plan_with_apex(valid_plan_dict, meta_version="58.0")
    xml = build_package_xml(plan)  # default DEFAULT_API_VERSION
    assert "<version>58.0</version>" in xml


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


# ---- deploy-time subset selection ------------------------------------------


def test_filter_by_step_numbers_excludes_unselected_step(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    # Keep only step 1's artifact.
    filtered = filter_plan_for_deploy(plan, step_numbers=[1])
    pkg = build_package_zip(filtered)
    assert pkg.steps_included == [1]
    assert (
        "objects/HealthCondition/fields/Diagnosis_Code__c.field-meta.xml"
        in pkg.file_paths
    )
    assert "permissionsets/PSL.permissionset-meta.xml" not in pkg.file_paths


def test_filter_does_not_mutate_input(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    filter_plan_for_deploy(plan, step_numbers=[1])
    # Original plan still has both artifacts.
    assert plan.steps[0].metadata_artifact is not None
    assert plan.steps[1].metadata_artifact is not None


def test_filter_by_artifact_paths_keeps_only_selected_file(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    keep = "permissionsets/PSL.permissionset-meta.xml"
    filtered = filter_plan_for_deploy(plan, artifact_paths=[keep])
    pkg = build_package_zip(filtered)
    assert pkg.file_paths == [keep]
    # package.xml should not list CustomField (its file was dropped).
    xml = build_package_xml(filtered)
    assert "<name>PermissionSet</name>" in xml
    assert "CustomField" not in xml


def test_filter_prunes_members_without_backing_file(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    filtered = filter_plan_for_deploy(plan, step_numbers=[2])
    xml = build_package_xml(filtered)
    assert "<members>PSL</members>" in xml
    assert "Diagnosis_Code__c" not in xml


def test_filter_empty_selection_yields_no_metadata(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    filtered = filter_plan_for_deploy(plan, step_numbers=[])
    with pytest.raises(NoDeployableMetadataError):
        build_package_zip(filtered)


def test_filter_none_is_noop(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    filtered = filter_plan_for_deploy(plan)  # both None
    pkg = build_package_zip(filtered)
    assert pkg.steps_included == [1, 2]


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
        # Matches the real simple_salesforce.Salesforce.deploy return shape.
        return {"asyncId": "0Af_ASYNC", "state": "Queued"}

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


def test_deploy_plan_accepts_tuple_return(valid_plan_dict):
    """Older simple_salesforce variants return a (asyncId, state) tuple."""
    plan = _plan_with_artifacts(valid_plan_dict)

    class _TupleSF(_FakeSF):
        def deploy(self, zipfile_obj, sandbox, **kwargs):
            self.deploy_kwargs = {"sandbox": sandbox, **kwargs}
            return ("0Af_ASYNC", "Queued")

    sf = _TupleSF(states=["Succeeded"])
    async_id, status = deploy_plan(
        sf, plan, is_sandbox=True, poll_interval=0, _sleep=lambda s: None
    )
    assert async_id == "0Af_ASYNC"
    assert status["succeeded"] is True


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
