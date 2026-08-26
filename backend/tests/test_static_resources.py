"""Tests for Static Resource support: registry, resolution, and binary packaging.

An LLM cannot author a binary zipped Static Resource, so a plan step names known
libraries in ``static_resources`` and the backend materializes real zipped
``.resource`` artifacts. These tests cover the registry (valid zips), the
resolver that injects artifacts into a plan, and that the binary payload survives
the deploy package and both GitHub repo formats intact.
"""

import base64
import copy
import io
import zipfile

import pytest

from app.api.routes.planning import _resolve_static_resources
from app.schemas.plan import MetadataFile, Plan, validate_business_rules
from app.services import static_resources as sr
from app.services.deployer import build_package_zip
from app.services.packager import build_repo_artifact


def test_registry_lists_known_libraries():
    assert set(sr.known_keys()) == {"pdfjs", "pdflib"}
    assert sr.is_known("pdfjs")
    assert sr.is_known("PDFJS")  # case-insensitive
    assert not sr.is_known("jquery")


def test_pdfjs_resource_is_a_valid_zip_with_both_files():
    files = sr.resource_files("pdfjs")
    paths = {f["path"] for f in files}
    assert paths == {
        "staticresources/pdfjs.resource",
        "staticresources/pdfjs.resource-meta.xml",
    }
    blob = next(f for f in files if f["path"].endswith(".resource"))
    inner = zipfile.ZipFile(io.BytesIO(base64.b64decode(blob["body_base64"])))
    assert set(inner.namelist()) == {"pdf.min.js", "pdf.worker.min.js"}
    # Each vendored file is non-empty.
    assert all(inner.read(n) for n in inner.namelist())


def test_pdflib_resource_zip_and_meta_content_type():
    files = sr.resource_files("pdflib")
    meta = next(f for f in files if f["path"].endswith("-meta.xml"))
    assert "<contentType>application/zip</contentType>" in meta["body"]
    blob = next(f for f in files if f["path"].endswith(".resource"))
    inner = zipfile.ZipFile(io.BytesIO(base64.b64decode(blob["body_base64"])))
    assert inner.namelist() == ["pdf-lib.min.js"]


def test_resource_zip_is_deterministic():
    """Same library must yield identical bytes (reproducible deploys/commits)."""
    a = sr.resource_files("pdfjs")[0]["body_base64"]
    b = sr.resource_files("pdfjs")[0]["body_base64"]
    assert a == b


def test_resolver_materializes_declared_libraries(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["static_resources"] = ["pdfjs", "pdflib"]
    resolved = _resolve_static_resources(data)
    plan = Plan.model_validate(resolved)

    art = plan.steps[0].metadata_artifact
    paths = {f.path for f in art.files}
    assert "staticresources/pdfjs.resource" in paths
    assert "staticresources/pdflib.resource" in paths
    # Binary files are flagged; meta files are text.
    by_path = {f.path: f for f in art.files}
    assert by_path["staticresources/pdfjs.resource"].is_binary
    assert not by_path["staticresources/pdfjs.resource-meta.xml"].is_binary
    members = {(m.type, m.name) for m in art.members}
    assert ("StaticResource", "pdfjs") in members
    assert ("StaticResource", "pdflib") in members


def test_resolver_is_idempotent(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["static_resources"] = ["pdfjs"]
    once = _resolve_static_resources(copy.deepcopy(data))
    twice = _resolve_static_resources(once)
    plan = Plan.model_validate(twice)
    art = plan.steps[0].metadata_artifact
    # No duplicate resource files or members after resolving twice.
    res_files = [f for f in art.files if f.path == "staticresources/pdfjs.resource"]
    assert len(res_files) == 1
    members = [m for m in art.members if m.name == "pdfjs"]
    assert len(members) == 1


def test_resolver_skips_unknown_key(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["static_resources"] = ["nope"]
    resolved = _resolve_static_resources(data)
    plan = Plan.model_validate(resolved)
    art = plan.steps[0].metadata_artifact
    # Unknown key contributes nothing (no crash, no artifact).
    if art:
        assert not any("nope" in f.path for f in art.files)


def test_binary_resource_survives_deploy_package(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["static_resources"] = ["pdfjs"]
    plan = Plan.model_validate(_resolve_static_resources(data))

    pkg = build_package_zip(plan, api_version="67.0")
    zf = zipfile.ZipFile(io.BytesIO(pkg.zip_bytes))
    # The .resource in the package is itself a valid, uncorrupted zip.
    inner = zipfile.ZipFile(io.BytesIO(zf.read("staticresources/pdfjs.resource")))
    assert set(inner.namelist()) == {"pdf.min.js", "pdf.worker.min.js"}
    assert "StaticResource" in zf.read("package.xml").decode()


def test_invalid_base64_binary_body_raises(valid_plan_dict):
    """A binary file with corrupt base64 fails the package build loudly."""
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0].setdefault("metadata_artifact", {"files": [], "members": []})
    data["steps"][0]["metadata_artifact"]["files"].append(
        {"path": "staticresources/bad.resource", "body_base64": "not!base64!!"}
    )
    data["steps"][0]["metadata_artifact"]["members"].append(
        {"type": "StaticResource", "name": "bad"}
    )
    plan = Plan.model_validate(data)
    with pytest.raises(ValueError, match="invalid base64"):
        build_package_zip(plan, api_version="67.0")


def test_business_rule_rejects_file_with_both_bodies(valid_plan_dict):
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0].setdefault("metadata_artifact", {"files": [], "members": []})
    data["steps"][0]["metadata_artifact"]["files"].append(
        {"path": "x.resource", "body": "text", "body_base64": "AAAA"}
    )
    plan = Plan.model_validate(data)
    errors = validate_business_rules(plan)
    assert any("both body and body_base64" in e for e in errors)


@pytest.mark.parametrize("fmt", ["mdapi", "sfdx"])
def test_repo_artifact_marks_binary_paths(valid_plan_dict, fmt):
    data = copy.deepcopy(valid_plan_dict)
    data["steps"][0]["static_resources"] = ["pdfjs"]
    plan = Plan.model_validate(_resolve_static_resources(data))

    art = build_repo_artifact(plan, fmt)
    # The .resource path is marked binary (committed as base64, not utf-8).
    res_paths = [p for p, _ in art.files if p.endswith("pdfjs.resource")]
    assert len(res_paths) == 1
    assert res_paths[0] in art.binary_paths
    # The meta file is NOT binary.
    meta_paths = [p for p, _ in art.files if p.endswith("pdfjs.resource-meta.xml")]
    assert meta_paths and meta_paths[0] not in art.binary_paths
    # The stored binary content is valid base64 of a real zip.
    content = dict(art.files)[res_paths[0]]
    inner = zipfile.ZipFile(io.BytesIO(base64.b64decode(content)))
    assert set(inner.namelist()) == {"pdf.min.js", "pdf.worker.min.js"}
