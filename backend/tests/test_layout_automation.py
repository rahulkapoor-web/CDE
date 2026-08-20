"""Tests for page-layout automation support.

Covers: extracting Layout XML from a retrieve zip, the SOAP fullName parser,
the packager mapping Layout files for both formats, and the prompt embedding
existing layout XML so the model can modify the real layout.
"""

import io
import zipfile

from app.connectors.salesforce import (
    _extract_layouts_from_zip,
    _layouts_from_read_response,
    _soap_findall_fullnames,
)
from app.schemas.plan import Plan
from app.schemas.planning import PlanningContext
from app.services.packager import _to_sfdx_paths, build_repo_artifact
from app.services.prompt import build_user_prompt

_LAYOUT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    "  <layoutSections><label>Additional Information</label></layoutSections>\n"
    "</Layout>\n"
)


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, body in files.items():
            zf.writestr(path, body)
    return buf.getvalue()


def test_extract_layouts_single_package():
    zip_bytes = _make_zip(
        {"layouts/Account-Account Layout.layout": _LAYOUT_XML}
    )
    out = _extract_layouts_from_zip(zip_bytes)
    assert "Account-Account Layout" in out
    assert "Additional Information" in out["Account-Account Layout"]


def test_extract_layouts_unpackaged_prefix():
    zip_bytes = _make_zip(
        {"unpackaged/layouts/Contact-Contact Layout.layout": _LAYOUT_XML}
    )
    out = _extract_layouts_from_zip(zip_bytes)
    assert "Contact-Contact Layout" in out


def test_layouts_from_read_response_builds_deployable_layout():
    # Mimics a readMetadata response: each layout is a <records> element with a
    # <fullName> plus body. The parser must yield a standalone .layout doc with
    # fullName stripped and the required Name item preserved.
    resp = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns="http://soap.sforce.com/2006/04/metadata" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<soapenv:Body><readMetadataResponse><result>"
        '<records xsi:type="Layout">'
        "<fullName>Account-Account Layout</fullName>"
        "<layoutSections><label>Account Information</label>"
        "<layoutColumns><layoutItems>"
        "<behavior>Required</behavior><field>Name</field>"
        "</layoutItems></layoutColumns></layoutSections>"
        "</records>"
        "</result></readMetadataResponse></soapenv:Body></soapenv:Envelope>"
    )
    out = _layouts_from_read_response(resp)
    assert "Account-Account Layout" in out
    xml = out["Account-Account Layout"]
    assert xml.startswith('<?xml version="1.0"')
    assert "<field>Name</field>" in xml
    # fullName is not part of a .layout body.
    assert "<fullName>" not in xml
    # Root is Layout and it parses.
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml)
    assert root.tag.endswith("Layout")


def test_layouts_from_read_response_handles_multiple_records():
    ns = 'xmlns="http://soap.sforce.com/2006/04/metadata"'
    resp = (
        f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" {ns}>'
        "<soapenv:Body><readMetadataResponse><result>"
        "<records><fullName>Account-Account Layout</fullName>"
        "<layoutSections><label>A</label></layoutSections></records>"
        "<records><fullName>Contact-Contact Layout</fullName>"
        "<layoutSections><label>B</label></layoutSections></records>"
        "</result></readMetadataResponse></soapenv:Body></soapenv:Envelope>"
    )
    out = _layouts_from_read_response(resp)
    assert set(out) == {"Account-Account Layout", "Contact-Contact Layout"}


def test_soap_findall_fullnames():
    xml = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soapenv:Body><listMetadataResponse '
        'xmlns="http://soap.sforce.com/2006/04/metadata">'
        "<result><fullName>Account-Account Layout</fullName></result>"
        "<result><fullName>Contact-Contact Layout</fullName></result>"
        "</listMetadataResponse></soapenv:Body></soapenv:Envelope>"
    )
    names = _soap_findall_fullnames(xml)
    assert names == ["Account-Account Layout", "Contact-Contact Layout"]


def test_packager_maps_layout_for_both_formats(valid_plan_dict):
    import copy

    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["metadata_artifact"] = {
        "files": [
            {"path": "layouts/Account-Account Layout.layout", "body": _LAYOUT_XML}
        ],
        "members": [{"type": "Layout", "name": "Account-Account Layout"}],
        "api_version": "60.0",
    }
    plan = Plan.model_validate(data)

    mdapi = {p for p, _ in build_repo_artifact(plan, "mdapi").files}
    assert "src/layouts/Account-Account Layout.layout" in mdapi

    sfdx = {p for p, _ in build_repo_artifact(plan, "sfdx").files}
    assert (
        "force-app/main/default/layouts/Account-Account Layout.layout-meta.xml"
        in sfdx
    )


def test_prompt_includes_existing_layout_xml():
    ctx = PlanningContext(
        jira_ticket_id="LSC-1",
        jira_summary="Add Specialty to Account",
        existing_layouts={"Account-Account Layout": _LAYOUT_XML},
    )
    prompt = build_user_prompt(ctx, guide_context="", has_images=False)
    assert "EXISTING PAGE LAYOUTS" in prompt
    assert "Account-Account Layout" in prompt
    assert "Additional Information" in prompt
    # It must instruct automation, not a manual step.
    assert "deployable metadata" in prompt


def test_to_sfdx_paths_layout():
    r = _to_sfdx_paths("layouts/Account-Account Layout.layout", _LAYOUT_XML)
    assert list(r.keys()) == [
        "force-app/main/default/layouts/Account-Account Layout.layout-meta.xml"
    ]
