"""Merge declarative layout edits into an existing Layout's XML.

A ``Layout`` deploy REPLACES the whole layout, so the deployed XML must contain
every item the org requires (e.g. the ``Name`` field). Rather than trust the LLM
to reproduce the full layout — which drops required items and fails with errors
like *"Layout must contain an item for required layout field: Name"* — we start
from the REAL layout XML retrieved from the org and only insert the requested
fields into the requested section. Everything else is preserved verbatim.

This module is pure (no I/O) and unit-tested.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.schemas.plan import LayoutEdit

_NS = "http://soap.sforce.com/2006/04/metadata"
_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>\n'


def _q(tag: str) -> str:
    return f"{{{_NS}}}{tag}"


def _existing_field_names(root: ET.Element) -> set[str]:
    """All field API names already placed anywhere on the layout."""
    names: set[str] = set()
    for item in root.iter(_q("layoutItems")):
        fld = item.find(_q("field"))
        if fld is not None and fld.text:
            names.add(fld.text.strip())
    return names


def _find_section_by_label(root: ET.Element, label: str) -> ET.Element | None:
    target = label.casefold()
    for section in root.iter(_q("layoutSections")):
        lbl = section.find(_q("label"))
        if lbl is not None and (lbl.text or "").strip().casefold() == target:
            return section
    return None


def _first_column(section: ET.Element) -> ET.Element:
    col = section.find(_q("layoutColumns"))
    if col is None:
        col = ET.SubElement(section, _q("layoutColumns"))
    return col


def _make_layout_item(field: str, behavior: str) -> ET.Element:
    item = ET.Element(_q("layoutItems"))
    b = ET.SubElement(item, _q("behavior"))
    b.text = behavior or "Edit"
    f = ET.SubElement(item, _q("field"))
    f.text = field
    return item


def _new_section(root: ET.Element, label: str) -> ET.Element:
    """Append a new edit-page section with the given label and one column."""
    section = ET.SubElement(root, _q("layoutSections"))
    ET.SubElement(section, _q("editHeading")).text = "true"
    ET.SubElement(section, _q("detailHeading")).text = "true"
    ET.SubElement(section, _q("label")).text = label
    style = ET.SubElement(section, _q("style"))
    style.text = "OneColumn"
    col = ET.SubElement(section, _q("layoutColumns"))
    # Placeholder so Salesforce accepts an otherwise-empty column is unnecessary;
    # the caller adds items immediately after.
    _ = col
    return section


def merge_fields_into_layout(
    existing_xml: str,
    add_fields: list,
    default_section: str | None = None,
) -> str:
    """Return the full layout XML with ``add_fields`` inserted, nothing removed.

    ``add_fields`` is a list of LayoutFieldEdit (or dict-likes) with ``field``,
    optional ``section`` and ``behavior``. Fields already present anywhere on the
    layout are skipped (idempotent). Target section is resolved by label; if it
    does not exist it is created. Required items already in ``existing_xml`` are
    preserved because we never rebuild the layout from scratch.
    """
    ET.register_namespace("", _NS)
    root = ET.fromstring(existing_xml)
    present = _existing_field_names(root)

    for spec in add_fields:
        field = _spec_get(spec, "field")
        if not field or field in present:
            continue
        section_label = _spec_get(spec, "section") or default_section or "Information"
        behavior = _spec_get(spec, "behavior") or "Edit"

        section = _find_section_by_label(root, section_label)
        if section is None:
            section = _new_section(root, section_label)
        column = _first_column(section)
        column.append(_make_layout_item(field, behavior))
        present.add(field)

    body = ET.tostring(root, encoding="unicode")
    return _XML_DECL + body + "\n"


def _spec_get(spec, key: str):
    if isinstance(spec, dict):
        return spec.get(key)
    return getattr(spec, key, None)


def layout_full_name_to_path(layout_name: str) -> str:
    """MDAPI file path for a layout fullName (packager handles sfdx conversion)."""
    return f"layouts/{layout_name}.layout"


def resolve_layout_edit(
    edit: LayoutEdit, existing_layouts: dict[str, str]
) -> tuple[str, str] | None:
    """Resolve one LayoutEdit to a (path, full_xml) file, or None if unresolvable.

    Returns None when the layout's existing XML is not available (we refuse to
    fabricate a full layout, which would drop required items).
    """
    existing = existing_layouts.get(edit.layout_name)
    if not existing:
        return None
    merged = merge_fields_into_layout(existing, edit.add_fields)
    return layout_full_name_to_path(edit.layout_name), merged
