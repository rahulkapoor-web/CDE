"""Parse a local SFDX project source tree into a metadata snapshot.

Covers common metadata types: objects, fields, flows, Apex classes, permission
sets. Not exhaustive by design (see spec open questions).
"""

import xml.etree.ElementTree as ET
from pathlib import Path


def parse_sfdx_project(root_path: str) -> dict:
    root = Path(root_path)
    default = root / "force-app" / "main" / "default"
    base = default if default.exists() else root

    objects: list[str] = []
    fields: list[str] = []
    flows: list[str] = []
    apex: list[str] = []
    perms: list[str] = []

    objects_dir = base / "objects"
    if objects_dir.exists():
        for obj_dir in sorted(p for p in objects_dir.iterdir() if p.is_dir()):
            objects.append(obj_dir.name)
            fields_dir = obj_dir / "fields"
            if fields_dir.exists():
                for fld in sorted(fields_dir.glob("*.field-meta.xml")):
                    field_name = fld.name.replace(".field-meta.xml", "")
                    fields.append(f"{obj_dir.name}.{field_name}")

    flows_dir = base / "flows"
    if flows_dir.exists():
        flows = [f.name.replace(".flow-meta.xml", "") for f in sorted(flows_dir.glob("*.flow-meta.xml"))]

    classes_dir = base / "classes"
    if classes_dir.exists():
        apex = [c.stem for c in sorted(classes_dir.glob("*.cls"))]

    perms_dir = base / "permissionsets"
    if perms_dir.exists():
        perms = [
            p.name.replace(".permissionset-meta.xml", "")
            for p in sorted(perms_dir.glob("*.permissionset-meta.xml"))
        ]

    edition = _read_edition(root)

    return {
        "sf_org_edition": edition,
        "lsc_modules": [],
        "installed_packages": _read_packages(root),
        "metadata_objects": objects,
        "metadata_fields": fields,
        "metadata_flows": flows,
        "metadata_apex_classes": apex,
        "metadata_permission_sets": perms,
    }


def _read_edition(root: Path) -> str:
    scratch = root / "config" / "project-scratch-def.json"
    if scratch.exists():
        try:
            import json

            data = json.loads(scratch.read_text())
            return data.get("edition", "")
        except Exception:  # noqa: BLE001
            return ""
    return ""


def _read_packages(root: Path) -> list[str]:
    sfdx_project = root / "sfdx-project.json"
    if not sfdx_project.exists():
        return []
    try:
        import json

        data = json.loads(sfdx_project.read_text())
        deps = []
        for pkg in data.get("packageDirectories", []):
            for dep in pkg.get("dependencies", []) or []:
                if "package" in dep:
                    deps.append(dep["package"])
        return deps
    except Exception:  # noqa: BLE001
        return []
