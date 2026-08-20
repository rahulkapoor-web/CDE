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
import time
import zipfile
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from app.schemas.plan import Plan

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "60.0"

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


def build_package_xml(plan: Plan, api_version: str = DEFAULT_API_VERSION) -> str:
    """Render a package.xml from the merged members of all steps.

    api_version resolution: the first step artifact that specifies an
    ``api_version`` wins; otherwise the provided default is used.
    """
    for step in plan.steps:
        if step.metadata_artifact and step.metadata_artifact.api_version:
            api_version = step.metadata_artifact.api_version
            break

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
            if path in file_map and file_map[path] != f.body:
                raise ValueError(
                    f"Conflicting content for metadata file '{path}' across steps."
                )
            file_map[path] = f.body

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
