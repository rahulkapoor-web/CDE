"""Salesforce connector for live org metadata snapshots.

Uses simple-salesforce for REST/Tooling API access. Supports username+token and
OAuth access-token styles, and sandbox vs production.
"""

import logging

logger = logging.getLogger(__name__)


class SalesforceConnector:
    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        security_token: str | None = None,
        instance_url: str | None = None,
        access_token: str | None = None,
        is_sandbox: bool = False,
    ) -> None:
        self.username = username
        self.password = password
        self.security_token = security_token
        self.instance_url = instance_url
        self.access_token = access_token
        self.is_sandbox = is_sandbox
        self.sf = None

    def connect(self):
        from simple_salesforce import Salesforce

        domain = "test" if self.is_sandbox else "login"
        if self.access_token and self.instance_url:
            self.sf = Salesforce(
                instance_url=self.instance_url, session_id=self.access_token
            )
        else:
            self.sf = Salesforce(
                username=self.username,
                password=self.password,
                security_token=self.security_token or "",
                domain=domain,
            )
        return self.sf

    def test(self) -> dict:
        sf = self.connect()
        limits = sf.limits()
        return {"connected": True, "api_limits": list(limits.keys())[:3]}

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
