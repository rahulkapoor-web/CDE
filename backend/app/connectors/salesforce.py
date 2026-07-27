"""Salesforce connector for IQVIA OCEP on Sales Cloud.

Uses simple-salesforce for REST/Bulk API access and metadata introspection.
"""

import logging
from typing import Any, Generator

from simple_salesforce import Salesforce, SalesforceLogin, SFBulkHandler

from app.schemas.mapping import SchemaField, SchemaObject

logger = logging.getLogger(__name__)


class SalesforceConnector:
    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        security_token: str | None = None,
        instance_url: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        access_token: str | None = None,
        is_sandbox: bool = False,
    ):
        self.sf: Salesforce | None = None
        self._username = username
        self._password = password
        self._security_token = security_token
        self._instance_url = instance_url
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._access_token = access_token
        self._is_sandbox = is_sandbox

    def connect(self) -> dict:
        """Establish connection and return session info."""
        domain = "test" if self._is_sandbox else "login"

        if self._access_token and self._instance_url:
            self.sf = Salesforce(
                instance_url=self._instance_url,
                session_id=self._access_token,
            )
        elif self._consumer_key and self._consumer_secret:
            self.sf = Salesforce(
                username=self._username,
                password=self._password,
                security_token=self._security_token or "",
                consumer_key=self._consumer_key,
                consumer_secret=self._consumer_secret,
                domain=domain,
            )
        else:
            self.sf = Salesforce(
                username=self._username,
                password=self._password,
                security_token=self._security_token or "",
                domain=domain,
            )

        # Verify connection
        identity = self.sf.restful("", params=None)
        return {
            "org_id": getattr(self.sf, "sf_instance", "unknown"),
            "username": self._username,
            "api_version": self.sf.sf_version,
        }

    def test_connection(self) -> dict:
        """Test connectivity and return org info."""
        try:
            info = self.connect()
            limits = self.sf.limits()
            return {
                "success": True,
                "message": f"Connected to {info['org_id']}",
                "details": {
                    "org_id": info["org_id"],
                    "api_version": info["api_version"],
                    "daily_api_requests_remaining": limits.get(
                        "DailyApiRequests", {}
                    ).get("Remaining", "N/A"),
                },
            }
        except Exception as e:
            return {"success": False, "message": str(e), "details": None}

    def list_objects(self) -> list[dict]:
        """List all SObjects in the org."""
        self._ensure_connected()
        describe = self.sf.describe()
        objects = []
        for obj in describe["sobjects"]:
            if obj.get("queryable") and not obj.get("deprecatedAndHidden"):
                objects.append(
                    {
                        "name": obj["name"],
                        "label": obj["label"],
                        "custom": obj.get("custom", False),
                        "queryable": obj.get("queryable", False),
                    }
                )
        return objects

    def describe_object(self, object_name: str) -> SchemaObject:
        """Get full field-level metadata for an object."""
        self._ensure_connected()
        desc = getattr(self.sf, object_name).describe()
        fields = []
        for f in desc["fields"]:
            picklist_values = None
            if f["type"] == "picklist" or f["type"] == "multipicklist":
                picklist_values = [
                    pv["value"] for pv in f.get("picklistValues", []) if pv.get("active")
                ]
            ref_to = None
            if f.get("referenceTo"):
                ref_to = f["referenceTo"][0] if f["referenceTo"] else None

            fields.append(
                SchemaField(
                    name=f["name"],
                    label=f["label"],
                    field_type=f["type"],
                    is_required=not f.get("nillable", True) and not f.get("defaultedOnCreate", False),
                    is_unique=f.get("unique", False),
                    length=f.get("length"),
                    picklist_values=picklist_values,
                    reference_to=ref_to,
                )
            )

        return SchemaObject(
            name=desc["name"],
            label=desc["label"],
            fields=fields,
        )

    def get_record_count(self, object_name: str) -> int:
        """Get approximate record count for an object."""
        self._ensure_connected()
        result = self.sf.query(f"SELECT COUNT() FROM {object_name}")
        return result["totalSize"]

    def query_records(self, soql: str) -> Generator[dict, None, None]:
        """Execute a SOQL query and yield records with automatic pagination."""
        self._ensure_connected()
        result = self.sf.query(soql)
        while True:
            for record in result["records"]:
                record.pop("attributes", None)
                yield record
            if result.get("done"):
                break
            result = self.sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)

    def bulk_query(self, object_name: str, fields: list[str]) -> Generator[dict, None, None]:
        """Stream records using Bulk API 2.0 for large datasets.

        Yields records one at a time to avoid loading everything into memory.
        """
        self._ensure_connected()
        field_str = ", ".join(fields)
        soql = f"SELECT {field_str} FROM {object_name}"

        # Use query_all to handle large result sets with pagination
        result = self.sf.query(soql)
        while True:
            for record in result["records"]:
                record.pop("attributes", None)
                yield record
            if result.get("done"):
                break
            result = self.sf.query_more(result["nextRecordsUrl"], identifier_is_url=True)

    def _ensure_connected(self):
        if self.sf is None:
            self.connect()
