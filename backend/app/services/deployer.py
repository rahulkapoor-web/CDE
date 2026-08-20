"""Build and deploy a Metadata API package from an approved plan.

A plan's steps may each carry a ``metadata_artifact`` (files + package.xml
members). This module merges every step's artifact into a single classic
Metadata API (MDAPI) package, zips it, and deploys it to a connected Salesforce
org via ``simple_salesforce.Salesforce.deploy`` (SOAP Metadata API — no CLI
required). Deployment is asynchronous; ``deploy_plan`` polls
``checkDeployStatus`` until the org reports a terminal state.

Packaging (``build_package_zip``) is pure and side-effect free so it can be unit
tested without a live org. The deploy call is isolated in ``deploy_plan``.
"""

from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from app.schemas.plan import Plan

logger = logging.getLogger(__name__)

_MDAPI_NS = "http://soap.sforce.com/2006/04/metadata"

# MDAPI metadata types whose single file aggregates many child members (e.g. a
# CustomObject file holds all fields, validationRules, listViews...). When two
# steps each emit the same such file with different children, they must be MERGED
# into one file rather than rejected as conflicting.
_MERGEABLE_SUFFIXES = (".object", ".object-meta.xml")

DEFAULT_API_VERSION = "60.0"

# Matches the version element inside Apex/LWC/Aura meta files, e.g.
# <apiVersion>60.0</apiVersion>. Case-insensitive on the tag so both the
# metadata <apiVersion> and any stray <version> in a meta file are normalized.
_API_VERSION_RE = re.compile(
    r"(<(?P<tag>apiVersion|version)>)\s*[\d.]+\s*(</(?P=tag)>)",
    re.IGNORECASE,
)

# Terminal deploy states reported by the Metadata API.
_TERMINAL_STATES = {"Succeeded", "Failed", "Canceled", "SucceededPartial"}
_SUCCESS_STATES = {"Succeeded"}


class NoDeployableMetadataError(ValueError):
    """Raised when a plan has no metadata_artifact on any step."""


@dataclass
class DeployPackage:
    """A ready-to-deploy MDAPI package."""

    zip_bytes: bytes
    package_xml: str
    file_paths: list[str]
    # step_number -> the file paths contributed by that step (for reporting).
    steps_included: list[int] = field(default_factory=list)


def _collect_members(plan: Plan) -> dict[str, list[str]]:
    """Merge every step's members into {metadata_type: [unique fullNames]}."""
    by_type: dict[str, list[str]] = {}
    for step in plan.steps:
        art = step.metadata_artifact
        if not art:
            continue
        for member in art.members:
            names = by_type.setdefault(member.type, [])
            if member.name not in names:
                names.append(member.name)
    return by_type


def _is_mergeable(path: str) -> bool:
    """True for MDAPI files that aggregate child members (e.g. CustomObject)."""
    p = path.lower()
    return p.endswith(_MERGEABLE_SUFFIXES)


def _child_key(el: ET.Element) -> tuple[str, str]:
    """Identity of a CustomObject child for merge dedup.

    Uses the element tag plus its <fullName> (the member name Salesforce keys on,
    e.g. a field's API name). Children without a fullName fall back to their
    serialized text so identical singletons don't duplicate.
    """
    tag = el.tag.split("}")[-1]
    full = el.find(f"{{{_MDAPI_NS}}}fullName")
    if full is None:
        full = el.find("fullName")
    name = (full.text or "").strip() if full is not None else ""
    if not name:
        name = ET.tostring(el, encoding="unicode")
    return (tag, name)


def _merge_object_xml(existing: str, incoming: str) -> str:
    """Merge two CustomObject XML documents into one.

    A CustomObject `.object` file must contain ALL of an object's members (every
    field, validationRule, etc.). When separate plan steps each create a
    different member on the same object, they emit the same `objects/X.object`
    path with only their own child — deploying either alone, or rejecting them as
    "conflicting", is wrong. This unions their child elements (dedup by
    tag+fullName) so the object deploys with every member present.

    Falls back to raising on unparseable XML so genuine corruption still surfaces.
    """
    ET.register_namespace("", _MDAPI_NS)
    root_a = ET.fromstring(existing)
    root_b = ET.fromstring(incoming)

    seen = {_child_key(c) for c in list(root_a)}
    for child in list(root_b):
        key = _child_key(child)
        if key not in seen:
            root_a.append(child)
            seen.add(key)

    xml = ET.tostring(root_a, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml


def _is_meta_file(path: str) -> bool:
    """True for Apex/LWC/Aura meta files that carry an <apiVersion> element."""
    p = path.lower()
    return p.endswith("-meta.xml")


def _normalize_api_version_in_body(body: str, api_version: str) -> str:
    """Rewrite any <apiVersion>/<version> element in a meta file to the org's.

    LLM-authored Apex ``.cls-meta.xml`` and LWC ``.js-meta.xml`` files hardcode
    an apiVersion (often a stale default) that may not match the target org,
    which causes deploy failures and drives the fix-with-AI error loop. Forcing
    every meta file to the org's real API version at build time makes deploys
    deterministic regardless of what the model emitted.
    """
    return _API_VERSION_RE.sub(
        lambda m: f"{m.group(1)}{api_version}{m.group(3)}", body
    )


def _sanitize_weblink_positions(body: str) -> str:
    """Drop ``<position>`` from WebLinks whose openType forbids it.

    Salesforce rejects a WebLink that specifies a field position when its
    ``openType`` is ``replace`` or ``onClickJavaScript`` with
    *"Field Position must not be specified for web links if the open type is
    Replace or On Click JavaScript"*. The LLM regularly emits a default
    ``<position>`` regardless of openType, driving the fix-with-AI loop. This
    strips the offending element at build time so the deploy is deterministic.

    Operates on CustomObject bodies (WebLinks live inside ``objects/*.object``).
    Returns the body unchanged if it does not parse or has no such WebLinks.
    """
    if "webLinks" not in body or "position" not in body:
        return body
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return body

    ns = f"{{{_MDAPI_NS}}}"
    changed = False
    for wl in root.findall(f"{ns}webLinks") + root.findall("webLinks"):
        open_el = wl.find(f"{ns}openType")
        if open_el is None:
            open_el = wl.find("openType")
        open_type = (open_el.text or "").strip().lower() if open_el is not None else ""
        if open_type not in ("replace", "onclickjavascript"):
            continue
        for pos in wl.findall(f"{ns}position") + wl.findall("position"):
            wl.remove(pos)
            changed = True

    if not changed:
        return body
    ET.register_namespace("", _MDAPI_NS)
    xml = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml


def _resolve_api_version(plan: Plan, api_version: str) -> str:
    """Pick the API version for the package.

    The caller-provided ``api_version`` (the org's real version, when known) is
    authoritative. Only when it is the built-in default do we fall back to the
    first artifact-specified version, so an explicitly passed org version always
    wins over whatever the LLM wrote.
    """
    if api_version and api_version != DEFAULT_API_VERSION:
        return api_version
    for step in plan.steps:
        if step.metadata_artifact and step.metadata_artifact.api_version:
            return step.metadata_artifact.api_version
    return api_version


def build_package_xml(plan: Plan, api_version: str = DEFAULT_API_VERSION) -> str:
    """Render a package.xml from the merged members of all steps.

    ``api_version`` is the org's real API version when known; it wins over any
    artifact-specified version so the package always targets the org's version.
    """
    api_version = _resolve_api_version(plan, api_version)

    by_type = _collect_members(plan)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<Package xmlns="http://soap.sforce.com/2006/04/metadata">')
    for mtype in sorted(by_type):
        lines.append("    <types>")
        for name in by_type[mtype]:
            lines.append(f"        <members>{escape(name)}</members>")
        lines.append(f"        <name>{escape(mtype)}</name>")
        lines.append("    </types>")
    lines.append(f"    <version>{escape(api_version)}</version>")
    lines.append("</Package>")
    return "\n".join(lines) + "\n"


def build_package_zip(
    plan: Plan, api_version: str = DEFAULT_API_VERSION
) -> DeployPackage:
    """Assemble the deployable zip for a plan.

    Raises NoDeployableMetadataError if no step carries a metadata_artifact.
    Raises ValueError on duplicate or empty file paths.
    """
    resolved_version = _resolve_api_version(plan, api_version)
    file_map: dict[str, str] = {}
    steps_included: list[int] = []

    for step in plan.steps:
        art = step.metadata_artifact
        if not art or not art.files:
            continue
        steps_included.append(step.step_number)
        for f in art.files:
            path = f.path.strip().lstrip("/")
            if not path:
                raise ValueError(
                    f"Step {step.step_number} has a metadata file with an empty path."
                )
            if path == "package.xml":
                raise ValueError(
                    "Steps must not provide package.xml; it is generated."
                )
            body = f.body
            # Force Apex/LWC meta files to the org's API version so a stale or
            # inconsistent LLM-authored apiVersion never fails the deploy.
            if _is_meta_file(path):
                body = _normalize_api_version_in_body(body, resolved_version)
            # Strip WebLink <position> when openType is replace/onClickJavaScript,
            # which Salesforce rejects. Object files carry WebLinks inline.
            if _is_mergeable(path):
                body = _sanitize_weblink_positions(body)
            if path in file_map and file_map[path] != body:
                # Aggregate metadata (e.g. a CustomObject holding both a new
                # field and a new validation rule from different steps) must be
                # merged into one file, not rejected — the object file must carry
                # every member or the deploy drops one.
                if _is_mergeable(path):
                    try:
                        file_map[path] = _merge_object_xml(file_map[path], body)
                        continue
                    except ET.ParseError as exc:
                        raise ValueError(
                            f"Could not merge metadata file '{path}' across "
                            f"steps: {exc}"
                        )
                raise ValueError(
                    f"Conflicting content for metadata file '{path}' across steps."
                )
            file_map[path] = body

    if not file_map:
        raise NoDeployableMetadataError(
            "This plan has no deployable metadata. All steps are manual "
            "(e.g. out-of-box enablement) and must be applied by hand."
        )

    package_xml = build_package_xml(plan, api_version=api_version)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", package_xml)
        for path, body in sorted(file_map.items()):
            zf.writestr(path, body)

    return DeployPackage(
        zip_bytes=buf.getvalue(),
        package_xml=package_xml,
        file_paths=sorted(file_map.keys()),
        steps_included=sorted(steps_included),
    )


def filter_plan_for_deploy(
    plan: Plan,
    step_numbers: list[int] | None = None,
    artifact_paths: list[str] | None = None,
) -> Plan:
    """Return a deep copy of ``plan`` narrowed to a user-selected subset.

    Selection is applied to each step's ``metadata_artifact``:

    * ``step_numbers`` (when not None): steps whose number is absent have their
      artifact removed entirely, so they contribute no files/members.
    * ``artifact_paths`` (when not None): within the remaining steps, only files
      whose path is in the set are kept. Package members are then pruned to the
      metadata types that still have at least one backing file in that step, so
      package.xml never lists a type with no deployable file.

    Passing ``None`` for a dimension means "no filtering on that dimension".
    Passing an empty list means "select nothing" for that dimension. The input
    plan is not mutated.
    """
    filtered = plan.model_copy(deep=True)
    step_set = set(step_numbers) if step_numbers is not None else None
    path_set = set(artifact_paths) if artifact_paths is not None else None

    def _norm(p: str) -> str:
        return p.strip().lstrip("/")

    for step in filtered.steps:
        art = step.metadata_artifact
        if not art:
            continue
        if step_set is not None and step.step_number not in step_set:
            step.metadata_artifact = None
            continue
        if path_set is not None:
            kept_files = [f for f in art.files if _norm(f.path) in path_set]
            art.files = kept_files
            # Prune members to types that still have a backing file. File paths
            # follow "<folder>/<Name>.<ext>"; the folder maps to a metadata type
            # only loosely, so we key on whether ANY file references the member
            # fullName, falling back to keeping members whose type still has
            # files at all.
            remaining_names = {
                _file_stem(f.path) for f in kept_files
            }
            pruned = []
            for m in art.members:
                if m.name in remaining_names or _member_has_file(m, kept_files):
                    pruned.append(m)
            art.members = pruned
    return filtered


def _file_stem(path: str) -> str:
    """Best-effort component fullName from a file path (strip dir + extensions)."""
    base = path.strip().lstrip("/").split("/")[-1]
    # Strip known compound extensions first (e.g. .layout-meta.xml, .object-meta.xml).
    for ext in (
        "-meta.xml",
    ):
        if base.endswith(ext):
            base = base[: -len(ext)]
    # Strip the remaining single extension.
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return base


def _member_has_file(member, files) -> bool:
    """True if any kept file path plausibly backs this member (by fullName)."""
    name = member.name
    for f in files:
        stem = _file_stem(f.path)
        if stem == name or name.endswith(stem) or stem.endswith(name):
            return True
    return False


def _normalize_status(raw: dict) -> dict:
    """Flatten checkDeployStatus output into a compact, JSON-serializable dict."""
    state = raw.get("state")
    dep = raw.get("deployment_detail") or {}
    tests = raw.get("unit_test_detail") or {}
    return {
        "state": state,
        "state_detail": raw.get("state_detail"),
        "succeeded": state in _SUCCESS_STATES,
        "components_total": dep.get("total_count"),
        "components_deployed": dep.get("deployed_count"),
        "components_failed": dep.get("failed_count"),
        "component_errors": dep.get("errors") or [],
        "tests_total": tests.get("total_count"),
        "tests_failed": tests.get("failed_count"),
        "test_errors": tests.get("errors") or [],
    }


def deploy_plan(
    sf,
    plan: Plan,
    *,
    is_sandbox: bool,
    check_only: bool = False,
    api_version: str = DEFAULT_API_VERSION,
    poll_interval: float = 3.0,
    timeout: float = 600.0,
    _sleep=time.sleep,
) -> tuple[str, dict]:
    """Deploy a plan's merged metadata package to the org.

    ``sf`` is a connected ``simple_salesforce.Salesforce`` instance. Returns
    ``(async_id, normalized_status)``. Blocking (SOAP + polling); callers should
    run it in a worker thread (``asyncio.to_thread``).

    ``check_only=True`` runs a validation-only deploy (no changes committed),
    useful as a dry run before real deployment.
    """
    package = build_package_zip(plan, api_version=api_version)
    logger.info(
        "Deploying plan %s: %d files, steps %s, check_only=%s",
        plan.plan_id,
        len(package.file_paths),
        package.steps_included,
        check_only,
    )

    # simple_salesforce >= 1.12 returns a dict {"asyncId", "state"} from
    # deploy(); older/newer variants may return a tuple. Handle both.
    deploy_ret = sf.deploy(
        io.BytesIO(package.zip_bytes),
        sandbox=is_sandbox,
        checkOnly=check_only,
        rollbackOnError=True,
        singlePackage=True,
    )
    if isinstance(deploy_ret, dict):
        async_id = deploy_ret.get("asyncId") or deploy_ret.get("id")
    else:
        async_id = deploy_ret[0]
    if not async_id:
        raise RuntimeError(f"Deploy did not return an async id: {deploy_ret!r}")

    deadline = time.monotonic() + timeout
    status: dict = {}
    while True:
        raw = sf.checkDeployStatus(async_id)
        status = _normalize_status(raw)
        if status["state"] in _TERMINAL_STATES:
            break
        if time.monotonic() >= deadline:
            status["state"] = status["state"] or "Timeout"
            status["succeeded"] = False
            status["state_detail"] = (
                f"Polling timed out after {timeout:.0f}s; last state "
                f"{status['state']!r}."
            )
            break
        _sleep(poll_interval)

    status["async_id"] = async_id
    status["package_files"] = package.file_paths
    status["steps_included"] = package.steps_included
    return async_id, status
