"""Salesforce connector for live org metadata snapshots.

Authenticates via the OAuth2 REST token endpoint (``/services/oauth2/token``)
rather than the SOAP ``login()`` API, which is disabled by default in many orgs
(``INVALID_OPERATION: SOAP API login() is disabled``). The obtained access token
and instance URL are then handed to simple-salesforce for REST/Tooling access.

Supported ``auth_flow`` values:
  - ``client_credentials``: client_id + client_secret (server-to-server, runs as
    the Connected App's "Run As" user). Token endpoint is the org My Domain host.
  - ``password``: client_id + client_secret + username + password
    (+ optional security_token appended to the password). OAuth2 ROPC — the
    direct replacement for the disabled SOAP login.
  - ``jwt_bearer``: client_id + username + private_key (PEM). No secret stored.
  - ``access_token``: pre-obtained access_token + instance_url (no token call).
"""

import io
import logging
import time
import zipfile
from base64 import b64decode
from xml.sax.saxutils import escape

import httpx

from app.services.target_detection import detect_target_objects

logger = logging.getLogger(__name__)

_OAUTH_FLOWS = {"client_credentials", "password", "jwt_bearer", "access_token"}

_MD_NS = {
    "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
    "mt": "http://soap.sforce.com/2006/04/metadata",
}

# SOAP envelope to start a Metadata API retrieve for named components.
_RETRIEVE_MSG = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:retrieve><met:retrieveRequest>
      <met:apiVersion>{api_version}</met:apiVersion>
      <met:singlePackage>true</met:singlePackage>
      <met:unpackaged>{types}<met:version>{api_version}</met:version></met:unpackaged>
    </met:retrieveRequest></met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

_CHECK_RETRIEVE_MSG = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:checkRetrieveStatus><met:asyncProcessId>{async_id}</met:asyncProcessId><met:includeZip>true</met:includeZip></met:checkRetrieveStatus>
  </soapenv:Body>
</soapenv:Envelope>"""

_LIST_METADATA_MSG = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:listMetadata><met:queries><met:type>Layout</met:type></met:queries><met:asOfVersion>{api_version}</met:asOfVersion></met:listMetadata>
  </soapenv:Body>
</soapenv:Envelope>"""

# Synchronous read of named metadata components (no async retrieve/zip/poll).
# readMetadata accepts up to 10 fullNames per Layout call and returns each as a
# <records> element in the response body.
_READ_METADATA_MSG = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:readMetadata><met:type>Layout</met:type>{full_names}</met:readMetadata>
  </soapenv:Body>
</soapenv:Envelope>"""


class SalesforceConnector:
    def __init__(
        self,
        auth_flow: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        username: str | None = None,
        password: str | None = None,
        security_token: str | None = None,
        private_key: str | None = None,
        instance_url: str | None = None,
        access_token: str | None = None,
        is_sandbox: bool = False,
    ) -> None:
        self.auth_flow = (auth_flow or "client_credentials").strip()
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.security_token = security_token
        self.private_key = private_key
        self.instance_url = instance_url.rstrip("/") if instance_url else None
        self.access_token = access_token
        self.is_sandbox = is_sandbox
        self.sf = None

    @property
    def _login_host(self) -> str:
        return (
            "https://test.salesforce.com"
            if self.is_sandbox
            else "https://login.salesforce.com"
        )

    @property
    def _token_host(self) -> str:
        """Host to use for the token request.

        Prefer the org's My Domain (instance_url) when provided — modern orgs and
        External Client Apps often only issue tokens from the My Domain host, and
        the generic login/test host returns invalid_client_id. Fall back to the
        login/test host (sandbox-aware) when no instance_url is configured.
        """
        return self.instance_url or self._login_host

    def _build_jwt_assertion(self) -> str:
        from jose import jwt

        now = int(time.time())
        payload = {
            "iss": self.client_id,
            "sub": self.username,
            "aud": self._login_host,
            "exp": now + 300,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def _oauth_token(self) -> dict:
        """Exchange credentials for an access token via the REST token endpoint."""
        flow = self.auth_flow

        if flow == "client_credentials":
            if not (self.client_id and self.client_secret and self.instance_url):
                raise ValueError(
                    "client_credentials flow requires client_id, client_secret, "
                    "and instance_url"
                )
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        elif flow == "password":
            if not (
                self.client_id
                and self.client_secret
                and self.username
                and self.password
            ):
                raise ValueError(
                    "password flow requires client_id, client_secret, username, "
                    "and password"
                )
            data = {
                "grant_type": "password",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "username": self.username,
                "password": self.password + (self.security_token or ""),
            }
        elif flow == "jwt_bearer":
            if not (self.client_id and self.username and self.private_key):
                raise ValueError(
                    "jwt_bearer flow requires client_id, username, and private_key"
                )
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": self._build_jwt_assertion(),
            }
        else:
            raise ValueError(f"Unsupported auth_flow: {flow}")

        token_url = f"{self._token_host}/services/oauth2/token"
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code != 200:
            raise ValueError(
                f"OAuth2 token request to {token_url} failed "
                f"({resp.status_code}): {resp.text}"
            )
        return resp.json()

    def connect(self):
        from simple_salesforce import Salesforce

        if self.auth_flow == "access_token":
            if not (self.access_token and self.instance_url):
                raise ValueError(
                    "access_token flow requires access_token and instance_url"
                )
            self.sf = Salesforce(
                instance_url=self.instance_url, session_id=self.access_token
            )
            return self.sf

        token = self._oauth_token()
        access_token = token["access_token"]
        instance_url = token.get("instance_url") or self.instance_url
        if not instance_url:
            raise ValueError("OAuth2 response did not include instance_url")
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.sf = Salesforce(
            instance_url=self.instance_url, session_id=access_token
        )
        return self.sf

    def test(self) -> dict:
        sf = self.connect()
        limits = sf.limits()
        return {
            "connected": True,
            "auth_flow": self.auth_flow,
            "instance_url": self.instance_url,
            "api_limits": list(limits.keys())[:3],
        }

    def fetch_metadata(
        self,
        object_names: list[str] | None = None,
        focus_text: str | None = None,
    ) -> dict:
        """Return a metadata snapshot.

        ``object_names`` explicitly scopes which objects to describe. When it is
        not given, the snapshot defaults to custom + known-LSC objects. If
        ``focus_text`` (e.g. the JIRA story) is provided, objects the story
        references — including standard ones like ``Account`` that aren't custom
        — are pulled to the front of the (capped) field-describe loop so the
        story's fields are always captured, keeping the snapshot proportional to
        the change instead of describing arbitrary objects.
        """
        sf = self.connect()
        describe = sf.describe()
        sobjects = describe.get("sobjects", [])
        all_objects = [o["name"] for o in sobjects]

        objects = object_names or [
            o["name"]
            for o in sobjects
            if o.get("custom") or o["name"] in _LSC_OBJECT_HINTS
        ]

        # Prioritize story-referenced objects (and include standard targets that
        # the default custom/LSC filter would miss) so their fields survive the
        # cap below.
        if focus_text and not object_names:
            targets = detect_target_objects(focus_text, all_objects)
            if targets:
                ordered = list(dict.fromkeys(targets + objects))
                objects = ordered

        fields: list[str] = []
        for obj in objects[:25]:  # cap to keep snapshots manageable
            try:
                obj_desc = getattr(sf, obj).describe()
                for fld in obj_desc.get("fields", []):
                    fields.append(f"{obj}.{fld['name']}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("describe failed for %s: %s", obj, exc)

        flows = _query_names(sf, "SELECT DeveloperName FROM FlowDefinitionView", "DeveloperName")
        apex = _query_names(sf, "SELECT Name FROM ApexClass", "Name")
        perms = _query_names(
            sf, "SELECT Name FROM PermissionSet WHERE IsOwnedByProfile = false", "Name"
        )
        profiles = _query_names(sf, "SELECT Name FROM Profile", "Name")
        packages = _query_names(
            sf,
            "SELECT SubscriberPackage.Name FROM InstalledSubscriberPackage",
            "Name",
            nested="SubscriberPackage",
        )

        return {
            "sf_org_edition": describe.get("organizationType") or "",
            "sf_api_version": self.get_api_version(),
            "lsc_modules": _detect_lsc_modules(all_objects),
            "installed_packages": packages,
            "metadata_objects": objects,
            "metadata_fields": fields,
            "metadata_flows": flows,
            "metadata_apex_classes": apex,
            "metadata_permission_sets": perms,
            "metadata_profiles": profiles,
        }

    def get_api_version(self) -> str:
        """Return the org's highest supported API version (e.g. "62.0").

        Queries the unauthenticated ``/services/data/`` discovery endpoint, which
        lists every API version the org supports; the last entry is the newest.
        This is the org's real ceiling — authoring Apex/LWC against a version the
        org does not support (or a stale hardcoded default) causes deploy
        failures, so callers use this to ground metadata to the target org.
        Falls back to the client default on any error so callers never crash.
        """
        default = getattr(self.sf, "sf_version", "60.0") if self.sf else "60.0"
        base = self.instance_url
        token = self.access_token
        if not base or not token:
            return default
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(
                    f"{base}/services/data/",
                    headers={"Authorization": f"Bearer {token}"},
                )
            resp.raise_for_status()
            versions = resp.json()
            if isinstance(versions, list) and versions:
                # Pick the numerically highest "version" string.
                latest = max(
                    versions, key=lambda v: float(v.get("version", "0") or 0)
                )
                return str(latest.get("version") or default)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not determine org API version: %s", exc)
        return default

    def _metadata_soap_url(self) -> str:
        # simple-salesforce exposes sf_version on the connected client.
        version = getattr(self.sf, "sf_version", "60.0")
        return f"{self.instance_url}/services/Soap/m/{version}/"

    def list_layouts(
        self, object_names: list[str] | None = None, api_version: str = "60.0"
    ) -> list[str]:
        """List Layout full names, optionally filtered to given objects.

        Returns e.g. ``["Account-Account Layout", "Contact-Contact Layout"]``.
        Best-effort: returns an empty list on failure.
        """
        try:
            self.connect()
            body = _LIST_METADATA_MSG.format(
                session_id=self.access_token, api_version=api_version
            )
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.post(
                    self._metadata_soap_url(),
                    content=body.encode("utf-8"),
                    headers={
                        "Content-Type": "text/xml",
                        "SOAPAction": "listMetadata",
                    },
                )
                resp.raise_for_status()
            names = _soap_findall_fullnames(resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("listMetadata(Layout) failed: %s", exc)
            return []

        if object_names:
            wanted = {o.lower() for o in object_names}
            names = [n for n in names if n.split("-", 1)[0].lower() in wanted]
        return names

    def fetch_layouts(
        self, layout_full_names: list[str], api_version: str = "60.0"
    ) -> dict[str, str]:
        """Retrieve existing Layout XML by full name via the Metadata API.

        Uses the SYNCHRONOUS ``readMetadata`` call (not the async retrieve/zip/
        poll flow, whose queue can stay Pending for minutes on busy orgs). Reads
        return in well under a second and require no polling. ``readMetadata``
        accepts up to 10 fullNames per call, so we chunk.

        Returns ``{full_name: layout_xml}`` where each value is a standalone,
        deployable ``.layout`` document. The full XML lets the planner insert a
        field into the REAL layout (preserving existing sections/fields, e.g. the
        required ``Name`` item). Best-effort: on any failure returns an empty
        dict so context gathering still succeeds.
        """
        if not layout_full_names:
            return {}

        out: dict[str, str] = {}
        try:
            self.connect()
            session_id = self.access_token
            soap_url = self._metadata_soap_url()

            with httpx.Client(timeout=30, follow_redirects=True) as client:
                for i in range(0, len(layout_full_names), 10):
                    chunk = layout_full_names[i : i + 10]
                    full_names = "".join(
                        f"<met:fullNames>{escape(n)}</met:fullNames>" for n in chunk
                    )
                    body = _READ_METADATA_MSG.format(
                        session_id=session_id, full_names=full_names
                    )
                    resp = client.post(
                        soap_url,
                        content=body.encode("utf-8"),
                        headers={
                            "Content-Type": "text/xml",
                            "SOAPAction": "readMetadata",
                        },
                    )
                    resp.raise_for_status()
                    out.update(_layouts_from_read_response(resp.text))
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("Layout read failed: %s", exc)
            return out


_LSC_OBJECT_HINTS = {
    "AccountPlan",
    "Visit",
    "CallReport",
    "Referral",
    "CareRequest",
    "CarePlan",
    "WorkOrder",
    "ServiceAppointment",
}

_LSC_MODULE_MARKERS = {
    "Intelligent Sales": ["AccountPlan", "Visit", "CallReport"],
    "Referral Management": ["Referral", "CareRequest"],
    "Care Management": ["CarePlan"],
    "MedTech / Field Service": ["WorkOrder", "ServiceAppointment"],
}


def _detect_lsc_modules(all_objects: list[str]) -> list[str]:
    present = set(all_objects)
    modules = []
    for module, markers in _LSC_MODULE_MARKERS.items():
        if any(any(m in o for o in present) for m in markers):
            modules.append(module)
    return modules


def _soap_findtext(xml_text: str, path: str) -> str | None:
    import xml.etree.ElementTree as ET

    try:
        return ET.fromstring(xml_text).findtext(path, None, _MD_NS)
    except ET.ParseError:
        return None


def _soap_findall_fullnames(xml_text: str) -> list[str]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for result in root.iter("{http://soap.sforce.com/2006/04/metadata}result"):
        fn = result.findtext("mt:fullName", None, _MD_NS)
        if fn:
            out.append(fn)
    return out


def _layouts_from_read_response(xml_text: str) -> dict[str, str]:
    """Convert a readMetadata SOAP response into ``{full_name: layout_xml}``.

    readMetadata returns each layout as a ``<records xsi:type="Layout">`` element
    containing a ``<fullName>`` plus the layout body. We rebuild each as a
    standalone, deployable ``<Layout>`` document (namespaced, ``fullName`` and
    xsi attributes dropped) so it round-trips through the same merge/deploy path
    as a retrieved ``.layout`` file.
    """
    import xml.etree.ElementTree as ET

    ns = "http://soap.sforce.com/2006/04/metadata"
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out

    for records in root.iter(f"{{{ns}}}records"):
        full_name = records.findtext(f"{{{ns}}}fullName", None, _MD_NS)
        if not full_name:
            continue
        ET.register_namespace("", ns)
        layout = ET.Element(f"{{{ns}}}Layout")
        for child in list(records):
            tag = child.tag
            # Skip the fullName element; it is not part of a .layout file body.
            if tag == f"{{{ns}}}fullName":
                continue
            layout.append(child)
        body = ET.tostring(layout, encoding="unicode")
        out[full_name] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
        )
    return out


def _extract_layouts_from_zip(zip_bytes: bytes) -> dict[str, str]:
    """Pull layout XML out of a retrieve zip, keyed by layout full name.

    In a singlePackage retrieve, layouts land under ``layouts/<FullName>.layout``.
    The full name is the file stem (e.g. ``Account-Account Layout``).
    """
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            norm = name.split("/", 1)[1] if name.startswith("unpackaged/") else name
            if norm.startswith("layouts/") and norm.endswith(".layout"):
                full_name = norm[len("layouts/") : -len(".layout")]
                out[full_name] = zf.read(name).decode("utf-8")
    return out


def _query_names(sf, soql: str, key: str, nested: str | None = None) -> list[str]:
    try:
        records = sf.query_all(soql).get("records", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("SOQL failed (%s): %s", soql, exc)
        return []
    names = []
    for rec in records:
        if nested:
            names.append((rec.get(nested) or {}).get(key, ""))
        else:
            names.append(rec.get(key, ""))
    return [n for n in names if n]
