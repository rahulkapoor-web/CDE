"""Tests for declarative layout_edits: merge, resolve, and generation hook.

The key invariant: a Layout deploy REPLACES the whole layout, so the merged
XML must retain every required item (e.g. Name) that the org's layout had. We
never rebuild a layout from scratch — we insert into the retrieved XML.
"""

import copy

from app.api.routes.planning import (
    _resolve_layout_edits,
    _resolve_layout_edits_live,
    _unresolved_layout_names,
)
from app.schemas.plan import LayoutEdit, LayoutFieldEdit
from app.schemas.planning import PlanningContext
from app.services.layout_merge import (
    merge_fields_into_layout,
    resolve_layout_edit,
)
from app.services.target_detection import detect_target_objects

# A realistic layout with a required Name item and an existing section.
_EXISTING_LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    "  <layoutSections>\n"
    "    <label>Account Information</label>\n"
    "    <layoutColumns>\n"
    "      <layoutItems>\n"
    "        <behavior>Required</behavior>\n"
    "        <field>Name</field>\n"
    "      </layoutItems>\n"
    "    </layoutColumns>\n"
    "  </layoutSections>\n"
    "  <layoutSections>\n"
    "    <label>Additional Information</label>\n"
    "    <layoutColumns>\n"
    "      <layoutItems>\n"
    "        <behavior>Edit</behavior>\n"
    "        <field>Description</field>\n"
    "      </layoutItems>\n"
    "    </layoutColumns>\n"
    "  </layoutSections>\n"
    "</Layout>\n"
)


def test_merge_preserves_required_name_item():
    merged = merge_fields_into_layout(
        _EXISTING_LAYOUT,
        [LayoutFieldEdit(field="Specialty__c", section="Additional Information")],
    )
    # Required Name item survives (this is the deploy-error fix).
    assert "<field>Name</field>" in merged
    assert "Required" in merged
    # New field added.
    assert "<field>Specialty__c</field>" in merged
    # Nothing dropped.
    assert "<field>Description</field>" in merged


def test_merge_into_named_existing_section():
    merged = merge_fields_into_layout(
        _EXISTING_LAYOUT,
        [LayoutFieldEdit(field="Specialty__c", section="Additional Information")],
    )
    # The new field lands under the existing "Additional Information" section,
    # not a duplicated one.
    assert merged.count("<label>Additional Information</label>") == 1


def test_merge_creates_missing_section():
    merged = merge_fields_into_layout(
        _EXISTING_LAYOUT,
        [LayoutFieldEdit(field="Special_Interest__c", section="New Section")],
    )
    assert "<label>New Section</label>" in merged
    assert "<field>Special_Interest__c</field>" in merged
    # Still preserves Name.
    assert "<field>Name</field>" in merged


def test_merge_is_idempotent_for_existing_field():
    merged = merge_fields_into_layout(
        _EXISTING_LAYOUT,
        [LayoutFieldEdit(field="Description", section="Additional Information")],
    )
    # Field already present anywhere on the layout -> not duplicated.
    assert merged.count("<field>Description</field>") == 1


def test_resolve_layout_edit_returns_path_and_xml():
    edit = LayoutEdit(
        layout_name="Account-Account Layout",
        add_fields=[LayoutFieldEdit(field="Specialty__c")],
    )
    result = resolve_layout_edit(
        edit, {"Account-Account Layout": _EXISTING_LAYOUT}
    )
    assert result is not None
    path, xml = result
    assert path == "layouts/Account-Account Layout.layout"
    assert "<field>Specialty__c</field>" in xml
    assert "<field>Name</field>" in xml


def test_resolve_layout_edit_none_when_xml_missing():
    edit = LayoutEdit(
        layout_name="Account-Account Layout",
        add_fields=[LayoutFieldEdit(field="Specialty__c")],
    )
    # No existing XML -> refuse to fabricate a partial layout.
    assert resolve_layout_edit(edit, {}) is None


# ---- target detection ------------------------------------------------------


def test_detect_target_objects_api_name():
    known = ["Account", "Contact", "Health_Condition__c", "Visit__c"]
    text = "Add a field to Health_Condition__c and place it on the layout"
    assert detect_target_objects(text, known) == ["Health_Condition__c"]


def test_detect_target_objects_standard_alias():
    known = ["Account", "Contact", "Visit__c"]
    text = "Add Specialty and Special Interest fields to the Account object"
    assert detect_target_objects(text, known) == ["Account"]


def test_detect_target_objects_multiple_preserves_order():
    known = ["Account", "Contact", "Visit__c"]
    text = "Update Contact and Account records"
    assert detect_target_objects(text, known) == ["Account", "Contact"]


def test_detect_target_objects_empty_when_no_match():
    known = ["Account", "Contact"]
    assert detect_target_objects("Refactor some Apex logic", known) == []


def test_detect_target_objects_handles_empty_inputs():
    assert detect_target_objects("", ["Account"]) == []
    assert detect_target_objects("Account", []) == []


# ---- generation hook -------------------------------------------------------


def _plan_with_layout_edit(valid_plan_dict: dict) -> dict:
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["layout_edits"] = [
        {
            "layout_name": "Account-Account Layout",
            "add_fields": [
                {
                    "field": "Specialty__c",
                    "section": "Additional Information",
                    "behavior": "Edit",
                }
            ],
        }
    ]
    return data


def test_resolve_layout_edits_injects_metadata_file(valid_plan_dict):
    data = _plan_with_layout_edit(valid_plan_dict)
    ctx = PlanningContext(
        existing_layouts={"Account-Account Layout": _EXISTING_LAYOUT}
    )
    out = _resolve_layout_edits(data, ctx)

    artifact = out["steps"][0]["metadata_artifact"]
    paths = {f["path"] for f in artifact["files"]}
    assert "layouts/Account-Account Layout.layout" in paths
    members = {(m["type"], m["name"]) for m in artifact["members"]}
    assert ("Layout", "Account-Account Layout") in members

    body = next(
        f["body"]
        for f in artifact["files"]
        if f["path"] == "layouts/Account-Account Layout.layout"
    )
    # Merged into the REAL layout: required Name preserved, new field present.
    assert "<field>Name</field>" in body
    assert "<field>Specialty__c</field>" in body


def test_resolve_layout_edits_skips_when_no_existing_xml(valid_plan_dict):
    data = _plan_with_layout_edit(valid_plan_dict)
    ctx = PlanningContext(existing_layouts={})
    out = _resolve_layout_edits(data, ctx)

    # No layout file fabricated; original artifact untouched (no Layout member).
    artifact = out["steps"][0].get("metadata_artifact") or {"members": []}
    members = {(m.get("type"), m.get("name")) for m in artifact.get("members", [])}
    assert ("Layout", "Account-Account Layout") not in members


def test_resolve_layout_edits_idempotent_no_duplicate_files(valid_plan_dict):
    data = _plan_with_layout_edit(valid_plan_dict)
    ctx = PlanningContext(
        existing_layouts={"Account-Account Layout": _EXISTING_LAYOUT}
    )
    out = _resolve_layout_edits(data, ctx)
    out = _resolve_layout_edits(out, ctx)
    artifact = out["steps"][0]["metadata_artifact"]
    layout_files = [
        f
        for f in artifact["files"]
        if f["path"] == "layouts/Account-Account Layout.layout"
    ]
    assert len(layout_files) == 1
    layout_members = [m for m in artifact["members"] if m["type"] == "Layout"]
    assert len(layout_members) == 1


# ---- deploy-time safety net (live resolution) ------------------------------


class _FakeConnector:
    """Minimal stand-in for SalesforceConnector used by the live resolver."""

    def __init__(self, layouts: dict[str, str]):
        self._layouts = layouts
        self.fetched_names: list[str] | None = None

    def connect(self):
        return self

    def list_layouts(self, object_names=None):
        return list(self._layouts.keys())

    def fetch_layouts(self, names, api_version="60.0"):
        self.fetched_names = list(names)
        return {n: self._layouts[n] for n in names if n in self._layouts}


def test_unresolved_layout_names_detects_missing_file(valid_plan_dict):
    data = _plan_with_layout_edit(valid_plan_dict)
    assert _unresolved_layout_names(data) == ["Account-Account Layout"]


def test_unresolved_layout_names_empty_when_resolved(valid_plan_dict):
    data = _plan_with_layout_edit(valid_plan_dict)
    ctx = PlanningContext(
        existing_layouts={"Account-Account Layout": _EXISTING_LAYOUT}
    )
    resolved = _resolve_layout_edits(data, ctx)
    assert _unresolved_layout_names(resolved) == []


def test_resolve_live_fetches_and_merges_from_target_org(valid_plan_dict):
    # Simulates the real bug: stored context had NO existing_layouts, so the
    # plan reached deploy with an unresolved layout_edit. The safety net must
    # fetch the real layout from the target org and produce a deployable file.
    data = _plan_with_layout_edit(valid_plan_dict)
    assert _unresolved_layout_names(data)  # precondition: unresolved

    conn = _FakeConnector({"Account-Account Layout": _EXISTING_LAYOUT})
    out, changed = _resolve_layout_edits_live(data, conn)

    assert changed is True
    assert conn.fetched_names == ["Account-Account Layout"]
    artifact = out["steps"][0]["metadata_artifact"]
    body = next(
        f["body"]
        for f in artifact["files"]
        if f["path"] == "layouts/Account-Account Layout.layout"
    )
    assert "<field>Name</field>" in body  # required item preserved
    assert "<field>Specialty__c</field>" in body


def test_resolve_live_noop_when_already_resolved(valid_plan_dict):
    data = _plan_with_layout_edit(valid_plan_dict)
    ctx = PlanningContext(
        existing_layouts={"Account-Account Layout": _EXISTING_LAYOUT}
    )
    resolved = _resolve_layout_edits(data, ctx)

    conn = _FakeConnector({"Account-Account Layout": _EXISTING_LAYOUT})
    out, changed = _resolve_layout_edits_live(resolved, conn)

    assert changed is False
    assert conn.fetched_names is None  # never hit the org


def test_resolve_live_handles_org_without_layout(valid_plan_dict):
    data = _plan_with_layout_edit(valid_plan_dict)
    conn = _FakeConnector({})  # org returns nothing
    out, changed = _resolve_layout_edits_live(data, conn)
    assert changed is False
    # Still unresolved -> surfaced, not fabricated.
    assert _unresolved_layout_names(out) == ["Account-Account Layout"]
