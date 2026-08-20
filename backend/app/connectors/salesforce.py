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

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_OAUTH_FLOWS = {"client_credentials", "password", "jwt_bearer", "access_token"}


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

    def fetch_metadata(self, object_names: list[str] | None = None) -> dict:
        """Return a metadata snapshot. `object_names` optionally scopes fields."""
        sf = self.connect()
        describe = sf.describe()
        sobjects = describe.get("sobjects", [])
        all_objects = [o["name"] for o in sobjects]

        objects = object_names or [
            o["name"]
            for o in sobjects
            if o.get("custom") or o["name"] in _LSC_OBJECT_HINTS
        ]

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
        packages = _query_names(
            sf,
            "SELECT SubscriberPackage.Name FROM InstalledSubscriberPackage",
            "Name",
            nested="SubscriberPackage",
        )

        return {
            "sf_org_edition": describe.get("organizationType") or "",
            "lsc_modules": _detect_lsc_modules(all_objects),
            "installed_packages": packages,
            "metadata_objects": objects,
            "metadata_fields": fields,
            "metadata_flows": flows,
            "metadata_apex_classes": apex,
            "metadata_permission_sets": perms,
        }


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
