"""Tests for pre-deploy validation guards.

These guards catch self-inconsistent plans before the Metadata API rejects the
whole package with cascading, opaque errors:

* non-deployable OmniStudio types (``OmniFlexCard``/``OmniScript``/…) that fail
  with ``Unknown type name '…'`` and poison the entire package.xml, and
* custom objects referenced by a tab/layout/profile/permission-set but never
  created by any step and absent from the org (``no CustomObject named X found``).

Both were observed in a real failed deploy (plan referencing ``Received_Document__c``
with OmniStudio components). The regenerated plan that fixed it must pass clean.
"""

import copy

import pytest

from app.schemas.plan import Plan, validate_business_rules
from app.services.deploy_validation import (
    check_dangling_object_references,
    check_non_mdapi_types,
    validate_deployable,
)


def _plan(base: dict) -> Plan:
    return Plan.model_validate(copy.deepcopy(base))


def _set_artifact(data: dict, idx: int, files: list[dict], members: list[dict]) -> None:
    data["steps"][idx]["metadata_artifact"] = {
        "files": files,
        "members": members,
        "api_version": "60.0",
    }


# --------------------------------------------------------------------------- #
# Non-MDAPI (OmniStudio) type guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "mtype,name",
    [
        ("OmniFlexCard", "DocSplitClassify_Processor"),
        ("OmniScript", "DocSplitClassify_Processor"),
        ("OmniIntegrationProcedure", "DocSplitClassify_SaveDocument"),
        ("omniscript", "lowercased_type"),  # case-insensitive
        ("DataRaptor", "DR_Extract"),
    ],
)
def test_non_mdapi_member_type_flagged(valid_plan_dict, mtype, name):
    data = copy.deepcopy(valid_plan_dict)
    _set_artifact(
        data,
        0,
        files=[{"path": f"omniScripts/{name}.omniScript", "body": "<x/>"}],
        members=[{"type": mtype, "name": name}],
    )
    plan = _plan(data)
    errors = check_non_mdapi_types(plan)
    assert errors, f"{mtype} should be flagged"
    assert "not deployable" in errors[0]
    assert "LWC" in errors[0] or "Lightning Web Component" in errors[0]


def test_non_mdapi_flagged_by_folder_even_without_member(valid_plan_dict):
    """An OmniStudio file smuggled in without a matching member is still caught."""
    data = copy.deepcopy(valid_plan_dict)
    _set_artifact(
        data,
        0,
        files=[
            {"path": "omniFlexCards/Foo.omniFlexCard", "body": "<x/>"},
        ],
        members=[],  # no member declared
    )
    plan = _plan(data)
    errors = check_non_mdapi_types(plan)
    assert len(errors) == 1
    assert "OmniStudio file" in errors[0]


def test_non_mdapi_each_type_reported_once(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    _set_artifact(
        data,
        0,
        files=[{"path": "omniScripts/A.omniScript", "body": "<x/>"}],
        members=[
            {"type": "OmniScript", "name": "A"},
            {"type": "OmniScript", "name": "B"},  # duplicate type
        ],
    )
    plan = _plan(data)
    errors = check_non_mdapi_types(plan)
    assert len(errors) == 1  # deduped by canonical type


def test_standard_types_not_flagged(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    _set_artifact(
        data,
        0,
        files=[{"path": "classes/Foo.cls", "body": "public class Foo {}"}],
        members=[{"type": "ApexClass", "name": "Foo"}],
    )
    assert check_non_mdapi_types(_plan(data)) == []


def test_non_mdapi_surfaced_in_business_rules(valid_plan_dict):
    """Refinement feedback: OmniStudio types must appear in business-rule errors."""
    data = copy.deepcopy(valid_plan_dict)
    _set_artifact(
        data,
        0,
        files=[{"path": "omniScripts/A.omniScript", "body": "<x/>"}],
        members=[{"type": "OmniScript", "name": "A"}],
    )
    errors = validate_business_rules(_plan(data))
    assert any("not deployable" in e for e in errors)


# --------------------------------------------------------------------------- #
# Dangling custom-object reference guard
# --------------------------------------------------------------------------- #


def _tab_step(data: dict, idx: int, obj: str) -> None:
    _set_artifact(
        data,
        idx,
        files=[{"path": f"tabs/{obj}.tab", "body": f"<CustomTab><customObject>true</customObject></CustomTab>"}],
        members=[{"type": "CustomTab", "name": obj}],
    )


def _object_step(data: dict, idx: int, obj: str) -> None:
    _set_artifact(
        data,
        idx,
        files=[{"path": f"objects/{obj}.object", "body": f"<CustomObject><label>{obj}</label></CustomObject>"}],
        members=[{"type": "CustomObject", "name": obj}],
    )


def test_tab_references_object_never_created(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    _tab_step(data, 0, "Received_Document__c")
    errors = check_dangling_object_references(_plan(data), org_objects=[])
    assert len(errors) == 1
    assert "received_document__c" in errors[0].lower()
    assert "no step creates it" in errors[0]


def test_object_created_in_plan_satisfies_reference(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    _object_step(data, 0, "Received_Document__c")  # step 1 creates it
    _tab_step(data, 1, "Received_Document__c")  # step 2 references it
    assert check_dangling_object_references(_plan(data), org_objects=[]) == []


def test_object_present_in_org_satisfies_reference(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    _tab_step(data, 0, "Received_Document__c")
    # Object already exists in the connected org -> not flagged.
    errors = check_dangling_object_references(
        _plan(data), org_objects=["Received_Document__c", "Account"]
    )
    assert errors == []


def test_object_match_is_case_insensitive(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    _tab_step(data, 0, "Received_Document__c")
    errors = check_dangling_object_references(
        _plan(data), org_objects=["received_document__c"]
    )
    assert errors == []


def test_layout_reference_flagged(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    _set_artifact(
        data,
        0,
        files=[
            {
                "path": "layouts/Received_Document__c-Received Document Layout.layout",
                "body": "<Layout/>",
            }
        ],
        members=[
            {"type": "Layout", "name": "Received_Document__c-Received Document Layout"}
        ],
    )
    errors = check_dangling_object_references(_plan(data), org_objects=[])
    assert len(errors) == 1
    assert "received_document__c" in errors[0].lower()


def test_field_grant_does_not_flag_field_as_object(valid_plan_dict):
    """A <field>Obj__c.Field__c</field> grant must flag the OBJECT, not the field."""
    data = copy.deepcopy(valid_plan_dict)
    # Object is created, so its object-level reference is satisfied. The permset
    # grants a field on it; the field token (Classification__c) must NOT be
    # treated as a missing object.
    _object_step(data, 0, "Received_Document__c")
    body = (
        "<PermissionSet>"
        "<objectPermissions><object>Received_Document__c</object></objectPermissions>"
        "<fieldPermissions><field>Received_Document__c.Classification__c</field></fieldPermissions>"
        "</PermissionSet>"
    )
    _set_artifact(
        data,
        1,
        files=[{"path": "permissionsets/RD_Admin.permissionset", "body": body}],
        members=[{"type": "PermissionSet", "name": "RD_Admin"}],
    )
    errors = check_dangling_object_references(_plan(data), org_objects=[])
    assert errors == [], errors


def test_permset_object_grant_flagged_when_object_missing(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    body = (
        "<PermissionSet>"
        "<objectPermissions><object>Ghost__c</object></objectPermissions>"
        "</PermissionSet>"
    )
    _set_artifact(
        data,
        0,
        files=[{"path": "permissionsets/RD_Admin.permissionset", "body": body}],
        members=[{"type": "PermissionSet", "name": "RD_Admin"}],
    )
    errors = check_dangling_object_references(_plan(data), org_objects=[])
    assert len(errors) == 1
    assert "ghost__c" in errors[0].lower()


def test_org_unknown_still_flags_uncreated_reference(valid_plan_dict):
    """When org state is unknown (None), an uncreated reference is still flagged."""
    data = copy.deepcopy(valid_plan_dict)
    _tab_step(data, 0, "Received_Document__c")
    errors = check_dangling_object_references(_plan(data), org_objects=None)
    assert len(errors) == 1


# --------------------------------------------------------------------------- #
# Combined entry point
# --------------------------------------------------------------------------- #


def test_validate_deployable_combines_both_guards(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    # OmniStudio member + a tab referencing an uncreated object.
    _set_artifact(
        data,
        0,
        files=[{"path": "omniScripts/A.omniScript", "body": "<x/>"}],
        members=[{"type": "OmniScript", "name": "A"}],
    )
    _tab_step(data, 1, "Ghost__c")
    errors = validate_deployable(_plan(data), org_objects=[])
    assert any("not deployable" in e for e in errors)
    assert any("ghost__c" in e.lower() for e in errors)


def test_clean_plan_passes(valid_plan_dict):
    """A plan that creates its object and uses only MDAPI types has no errors."""
    data = copy.deepcopy(valid_plan_dict)
    _object_step(data, 0, "Received_Document__c")
    _tab_step(data, 1, "Received_Document__c")
    assert validate_deployable(_plan(data), org_objects=[]) == []
