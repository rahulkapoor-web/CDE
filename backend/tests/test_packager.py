"""Tests for rendering a plan's metadata into repo files (mdapi / sfdx).

Packaging is pure, so these run without a live org or GitHub. They assert the
MDAPI->source decomposition (inline <fields> become per-field files) and the
MDAPI layout (src/ root + generated package.xml).
"""

import copy

import pytest

from app.connectors.github import detect_format_from_paths
from app.schemas.plan import Plan
from app.services.deployer import NoDeployableMetadataError
from app.services.packager import build_repo_artifact

_ACCOUNT_OBJECT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    "  <fields>\n"
    "    <fullName>ACV__c</fullName>\n"
    "    <label>ACV</label>\n"
    "    <type>Currency</type>\n"
    "    <precision>16</precision>\n"
    "    <scale>2</scale>\n"
    "  </fields>\n"
    "  <fields>\n"
    "    <fullName>Region__c</fullName>\n"
    "    <label>Region</label>\n"
    "    <type>Text</type>\n"
    "    <length>80</length>\n"
    "  </fields>\n"
    "</CustomObject>\n"
)

_PERMSET = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    "  <label>Care Coordinator</label>\n"
    "</PermissionSet>\n"
)


def _plan_with_artifacts(base: dict) -> Plan:
    data = copy.deepcopy(base)
    data["steps"][0]["metadata_artifact"] = {
        "files": [{"path": "objects/Account.object", "body": _ACCOUNT_OBJECT}],
        "members": [
            {"type": "CustomField", "name": "Account.ACV__c"},
            {"type": "CustomField", "name": "Account.Region__c"},
        ],
        "api_version": "60.0",
    }
    data["steps"][1]["metadata_artifact"] = {
        "files": [
            {"path": "permissionsets/PSL_Care.permissionset", "body": _PERMSET}
        ],
        "members": [{"type": "PermissionSet", "name": "PSL_Care"}],
        "api_version": "60.0",
    }
    return Plan.model_validate(data)


def test_mdapi_format_includes_package_xml_and_src_root(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    art = build_repo_artifact(plan, "mdapi")

    paths = {p for p, _ in art.files}
    assert "src/package.xml" in paths
    assert "src/objects/Account.object" in paths
    assert "src/permissionsets/PSL_Care.permissionset" in paths
    assert art.package_xml and "CustomField" in art.package_xml


def test_sfdx_format_decomposes_object_into_field_files(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    art = build_repo_artifact(plan, "sfdx")

    paths = {p for p, _ in art.files}
    # Each inline <fields> becomes its own -meta.xml file under fields/.
    assert (
        "force-app/main/default/objects/Account/fields/ACV__c.field-meta.xml"
        in paths
    )
    assert (
        "force-app/main/default/objects/Account/fields/Region__c.field-meta.xml"
        in paths
    )
    # Non-decomposed types get a -meta.xml suffix under the source root.
    assert (
        "force-app/main/default/permissionsets/PSL_Care.permissionset-meta.xml"
        in paths
    )
    # Source format has no package.xml.
    assert art.package_xml is None

    # A field file's content is wrapped in <CustomField> and carries the field.
    field_body = dict(art.files)[
        "force-app/main/default/objects/Account/fields/ACV__c.field-meta.xml"
    ]
    assert "<CustomField" in field_body
    assert "ACV__c" in field_body


def test_no_metadata_raises(valid_plan_dict):
    plan = Plan.model_validate(valid_plan_dict)  # no artifacts
    with pytest.raises(NoDeployableMetadataError):
        build_repo_artifact(plan, "sfdx")


def test_unknown_format_rejected(valid_plan_dict):
    plan = _plan_with_artifacts(valid_plan_dict)
    with pytest.raises(ValueError):
        build_repo_artifact(plan, "bogus")


def test_detect_format_from_paths():
    assert detect_format_from_paths(["sfdx-project.json", "README.md"]) == "sfdx"
    assert (
        detect_format_from_paths(["force-app/main/default/x.cls"]) == "sfdx"
    )
    assert detect_format_from_paths(["src/package.xml"]) == "mdapi"
    assert detect_format_from_paths(["docs/readme.md"]) == "unknown"
