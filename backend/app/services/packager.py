"""Render a plan's metadata artifacts as repository files for a GitHub commit.

Plan steps author metadata in classic Metadata API (MDAPI) format (see the
system prompt and ``deployer.py``). To commit into a developer's repo for review,
we render those same artifacts in the layout the repo uses:

* ``mdapi`` — the files as authored under a ``src/`` root, plus a generated
  ``src/package.xml`` (the classic Ant/Metadata API layout).
* ``sfdx`` — SFDX *source* format under ``force-app/main/default/``. Object files
  with inline ``<fields>`` (and similar) children are decomposed into the
  per-component files SFDX expects (e.g. ``objects/Account/fields/X.field-meta.xml``);
  other types get the ``-meta.xml`` suffix and standard subfolder.

Everything here is pure (no network/org I/O) so it is unit-testable. The GitHub
commit endpoint feeds the resulting files to the connector.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from app.schemas.plan import Plan
from app.services.deployer import (
    DEFAULT_API_VERSION,
    NoDeployableMetadataError,
    build_package_xml,
)

_NS = "http://soap.sforce.com/2006/04/metadata"
_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>\n'

SFDX_ROOT = "force-app/main/default"
MDAPI_ROOT = "src"

# CustomObject child elements that SFDX source format decomposes into their own
# files: local tag -> (subfolder, wrapper root element, file suffix).
_OBJECT_DECOMPOSE: dict[str, tuple[str, str, str]] = {
    "fields": ("fields", "CustomField", "field"),
    "validationRules": ("validationRules", "ValidationRule", "validationRule"),
    "listViews": ("listViews", "ListView", "listView"),
    "recordTypes": ("recordTypes", "RecordType", "recordType"),
    "webLinks": ("webLinks", "WebLink", "webLink"),
    "fieldSets": ("fieldSets", "FieldSet", "fieldSet"),
    "compactLayouts": ("compactLayouts", "CompactLayout", "compactLayout"),
    "businessProcesses": (
        "businessProcesses",
        "BusinessProcess",
        "businessProcess",
    ),
}

# Non-decomposed metadata: MDAPI folder -> the SFDX -meta.xml suffix to append.
# (The folder name is unchanged; SFDX just adds -meta.xml to the file.)
_META_SUFFIX_FOLDERS = {
    "permissionsets",
    "layouts",
    "flows",
    "objects",  # object-level file when not decomposed
    "labels",
    "tabs",
    "applications",
    "quickActions",
    "flexipages",
    "groups",
    "profiles",
}


@dataclass
class RepoArtifact:
    """Files to write to a repo, plus metadata about how they were rendered.

    ``files`` are ``(path, content)`` pairs. For binary artifacts (paths in
    ``binary_paths``) ``content`` is a base64 string; callers committing to a SCM
    must encode those blobs as base64 rather than utf-8. Text files carry their
    literal content.
    """

    fmt: str  # "mdapi" | "sfdx"
    files: list[tuple[str, str]] = field(default_factory=list)
    package_xml: str | None = None  # mdapi only
    members: list[str] = field(default_factory=list)  # "Type:name" for reporting
    binary_paths: set[str] = field(default_factory=set)


def _collect_files(plan: Plan) -> tuple[dict[str, str], set[str]]:
    """Merge every step's artifact files into {path: content}, like the deployer.

    Returns ``(file_map, binary_paths)``. Binary files (e.g. a zipped
    StaticResource) contribute their base64 string as content and their path is
    recorded in ``binary_paths`` so downstream committers encode them correctly.
    """
    file_map: dict[str, str] = {}
    binary_paths: set[str] = set()
    for step in plan.steps:
        art = step.metadata_artifact
        if not art or not art.files:
            continue
        for f in art.files:
            path = f.path.strip().lstrip("/")
            if not path or path == "package.xml":
                continue
            content = f.body_base64 if f.is_binary else f.body
            if path in file_map and file_map[path] != content:
                raise ValueError(
                    f"Conflicting content for metadata file '{path}' across steps."
                )
            file_map[path] = content
            if f.is_binary:
                binary_paths.add(path)
    return file_map, binary_paths


def _members(plan: Plan) -> list[str]:
    out: list[str] = []
    for step in plan.steps:
        art = step.metadata_artifact
        if not art:
            continue
        for m in art.members:
            label = f"{m.type}:{m.name}"
            if label not in out:
                out.append(label)
    return out


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _serialize(root: ET.Element) -> str:
    ET.register_namespace("", _NS)
    body = ET.tostring(root, encoding="unicode")
    return _XML_DECL + body + "\n"


def _decompose_object(object_name: str, body: str) -> dict[str, str]:
    """Split an MDAPI ``objects/<Object>.object`` file into SFDX source files.

    Returns {relative_path_under_objects_dir: body}. ``fields`` and similar child
    lists become individual files; remaining object-level elements are written to
    ``<Object>/<Object>.object-meta.xml``. If parsing fails, the caller falls
    back to writing the file whole.
    """
    root = ET.fromstring(body)
    base = f"objects/{object_name}"
    out: dict[str, str] = {}
    remaining: list[ET.Element] = []

    for child in list(root):
        ltag = _local(child.tag)
        spec = _OBJECT_DECOMPOSE.get(ltag)
        if not spec:
            remaining.append(child)
            continue
        subfolder, wrapper, suffix = spec
        full = child.find(f"{{{_NS}}}fullName")
        if full is None or not (full.text and full.text.strip()):
            # Can't name the file; keep it inline on the object.
            remaining.append(child)
            continue
        name = full.text.strip()
        new_root = ET.Element(f"{{{_NS}}}{wrapper}")
        for inner in list(child):
            new_root.append(inner)
        out[f"{base}/{subfolder}/{name}.{suffix}-meta.xml"] = _serialize(new_root)

    # Object-level remainder (or an empty CustomObject shell if there was any
    # object-level metadata) -> the object's own -meta.xml file.
    if remaining:
        obj_root = ET.Element(f"{{{_NS}}}CustomObject")
        for el in remaining:
            obj_root.append(el)
        out[f"{base}/{object_name}.object-meta.xml"] = _serialize(obj_root)

    return out


def _to_sfdx_paths(path: str, body: str) -> dict[str, str]:
    """Map one MDAPI file to one-or-more SFDX source files under SFDX_ROOT."""
    path = path.lstrip("/")

    # Already source-format-ish: pass through unchanged (best effort).
    if path.startswith("force-app/") or path.endswith("-meta.xml"):
        return {path: body}

    parts = path.split("/", 1)
    folder = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    # Objects: decompose inline children into per-component files.
    if folder == "objects" and rest.endswith(".object"):
        object_name = rest[: -len(".object")]
        try:
            decomposed = _decompose_object(object_name, body)
            if decomposed:
                return {f"{SFDX_ROOT}/{rel}": b for rel, b in decomposed.items()}
        except ET.ParseError:
            pass  # fall through to whole-file mapping below
        return {f"{SFDX_ROOT}/{path}-meta.xml": body}

    # Apex/LWC code files keep their real extension (no -meta.xml on the code).
    if folder == "classes" and (rest.endswith(".cls") or rest.endswith(".cls-meta.xml")):
        return {f"{SFDX_ROOT}/{path}": body}
    if folder == "triggers" and (
        rest.endswith(".trigger") or rest.endswith(".trigger-meta.xml")
    ):
        return {f"{SFDX_ROOT}/{path}": body}

    if folder in _META_SUFFIX_FOLDERS:
        return {f"{SFDX_ROOT}/{path}-meta.xml": body}

    # Unknown type: place under the source root unchanged so nothing is lost.
    return {f"{SFDX_ROOT}/{path}": body}


def build_repo_artifact(
    plan: Plan, fmt: str, api_version: str = DEFAULT_API_VERSION
) -> RepoArtifact:
    """Render a plan's metadata as repo files in ``fmt`` ("mdapi" | "sfdx").

    Raises ``NoDeployableMetadataError`` if the plan has no deployable metadata,
    and ``ValueError`` for an unknown format or conflicting file content.
    """
    if fmt not in ("mdapi", "sfdx"):
        raise ValueError(f"Unknown metadata format '{fmt}'. Use 'mdapi' or 'sfdx'.")

    file_map, binary_paths = _collect_files(plan)
    if not file_map:
        raise NoDeployableMetadataError(
            "This plan has no deployable metadata to commit. All steps are "
            "manual and must be applied by hand."
        )

    members = _members(plan)

    if fmt == "mdapi":
        package_xml = build_package_xml(plan, api_version=api_version)
        files = [(f"{MDAPI_ROOT}/package.xml", package_xml)]
        out_binary: set[str] = set()
        for path, body in sorted(file_map.items()):
            out_path = f"{MDAPI_ROOT}/{path}"
            files.append((out_path, body))
            if path in binary_paths:
                out_binary.add(out_path)
        return RepoArtifact(
            fmt=fmt,
            files=files,
            package_xml=package_xml,
            members=members,
            binary_paths=out_binary,
        )

    # sfdx source format
    out: dict[str, str] = {}
    out_binary = set()
    for path, body in file_map.items():
        # Binary artifacts (e.g. .resource zips) are not decomposed; place them
        # under the source root unchanged and mark them binary.
        if path in binary_paths:
            rel = f"{SFDX_ROOT}/{path}"
            out[rel] = body
            out_binary.add(rel)
            continue
        for rel, content in _to_sfdx_paths(path, body).items():
            if rel in out and out[rel] != content:
                raise ValueError(f"Conflicting content for source file '{rel}'.")
            out[rel] = content
    files = sorted(out.items())
    return RepoArtifact(
        fmt=fmt, files=files, members=members, binary_paths=out_binary
    )
