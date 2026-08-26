"""Server-side registry of known Static Resource libraries.

An LLM cannot author binary artifacts (a zipped JS library) inside a JSON plan,
and Lightning Web Security (LWS) rejects raw ``.js`` static resources with an
"Unsupported MIME type" error — third-party libraries such as PDF.js must be
uploaded as a ``application/zip`` StaticResource. This module bundles the real
library files (vendored under ``static_libs/vendor``) into deterministic zips at
build time and exposes them as deployable Metadata API artifacts.

A plan step declares which libraries it needs via ``static_resources: ["pdfjs"]``
(see ``PlanStep``); the backend materializes each into:

* ``staticresources/<name>.resource``          — the binary zip payload
* ``staticresources/<name>.resource-meta.xml``  — the StaticResource definition

plus a ``StaticResource`` package member. This mirrors how ``layout_edits`` are
resolved server-side rather than hand-authored by the LLM.

Static Resource names must be alphanumeric (no dots/dashes), so the registry key
IS the resource name (``pdfjs``, ``pdflib``).
"""

from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "static_libs" / "vendor"

# The StaticResource XML is deterministic; only the description varies.
_RESOURCE_META = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<StaticResource xmlns="http://soap.sforce.com/2006/04/metadata">\n'
    "    <cacheControl>Public</cacheControl>\n"
    "    <contentType>application/zip</contentType>\n"
    "    <description>{description}</description>\n"
    "</StaticResource>\n"
)


@dataclass(frozen=True)
class StaticLibrary:
    """A known third-party library packaged as a zipped StaticResource.

    ``name`` is the alphanumeric StaticResource name (and registry key).
    ``members`` maps the in-zip file name to the vendored source file name.
    """

    name: str
    description: str
    members: dict[str, str] = field(default_factory=dict)


# Registry of libraries the agent can request declaratively. Versions are pinned
# to the vendored files under static_libs/vendor.
_REGISTRY: dict[str, StaticLibrary] = {
    "pdfjs": StaticLibrary(
        name="pdfjs",
        description="PDF.js 2.6.347 with worker — bundled as zip for LWS compatibility",
        members={
            "pdf.min.js": "pdf.min.js",
            "pdf.worker.min.js": "pdf.worker.min.js",
        },
    ),
    "pdflib": StaticLibrary(
        name="pdflib",
        description="PDF-lib 1.17.1 — bundled as zip for LWS compatibility",
        members={"pdf-lib.min.js": "pdf-lib.min.js"},
    ),
}


def known_keys() -> list[str]:
    """Registry keys that a plan step may request in ``static_resources``."""
    return sorted(_REGISTRY)


def is_known(key: str) -> bool:
    return key.strip().lower() in _REGISTRY


def _build_zip(lib: StaticLibrary) -> bytes:
    """Zip a library's vendored files into a deterministic archive.

    Deterministic (fixed timestamps) so the same library always yields identical
    bytes, which keeps deploys and GitHub commits reproducible.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, source in sorted(lib.members.items()):
            src = _VENDOR_DIR / source
            data = src.read_bytes()
            info = zipfile.ZipInfo(filename=arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return buf.getvalue()


def resource_files(key: str) -> list[dict]:
    """Materialize a library into deployable Metadata API files.

    Returns a list of ``{"path", "body"?/"body_base64"?}`` dicts: the binary
    ``.resource`` (base64) and its text ``.resource-meta.xml``. Raises
    ``KeyError`` for an unknown key.
    """
    lib = _REGISTRY[key.strip().lower()]
    zip_bytes = _build_zip(lib)
    return [
        {
            "path": f"staticresources/{lib.name}.resource",
            "body_base64": base64.b64encode(zip_bytes).decode("ascii"),
        },
        {
            "path": f"staticresources/{lib.name}.resource-meta.xml",
            "body": _RESOURCE_META.format(description=lib.description),
        },
    ]


def resource_member(key: str) -> dict:
    """The package.xml member for a library's StaticResource."""
    lib = _REGISTRY[key.strip().lower()]
    return {"type": "StaticResource", "name": lib.name}
