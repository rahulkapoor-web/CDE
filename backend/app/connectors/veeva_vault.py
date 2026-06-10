"""Veeva Vault CRM connector.

Custom REST client for the Vault API since no official Python SDK exists.
Handles authentication, metadata introspection, and record queries.
"""

import logging
from typing import Any, Generator

import httpx

from app.schemas.mapping import SchemaField, SchemaObject

logger = logging.getLogger(__name__)

VAULT_API_VERSION = "v24.3"


class VeevaVaultConnector:
    def __init__(
        self,
        vault_dns: str | None = None,
        username: str | None = None,
        password: str | None = None,
        session_id: str | None = None,
    ):
        self._vault_dns = vault_dns.rstrip("/") if vault_dns else None
        self._username = username
        self._password = password
        self._session_id = session_id
        self._client: httpx.Client | None = None

    @property
    def base_url(self) -> str:
        return f"{self._vault_dns}/api/{VAULT_API_VERSION}"

    def connect(self) -> dict:
        """Authenticate and establish a session."""
        self._client = httpx.Client(timeout=120)

        if self._session_id:
            # Reuse existing session
            self._client.headers["Authorization"] = self._session_id
        else:
            # Authenticate with username/password
            auth_url = f"{self._vault_dns}/api/{VAULT_API_VERSION}/auth"
            resp = self._client.post(
                auth_url,
                data={"username": self._username, "password": self._password},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("responseStatus") != "SUCCESS":
                raise ConnectionError(
                    f"Vault auth failed: {data.get('errors', data.get('responseMessage', 'Unknown error'))}"
                )

            self._session_id = data["sessionId"]
            self._client.headers["Authorization"] = self._session_id

        return {"vault_dns": self._vault_dns, "session_id": "***"}

    def test_connection(self) -> dict:
        """Test connectivity and return vault info."""
        try:
            self.connect()
            # Fetch vault info
            resp = self._request("GET", f"{self.base_url}/objects")
            objects = resp.get("objects", [])
            return {
                "success": True,
                "message": f"Connected to {self._vault_dns}",
                "details": {
                    "vault_dns": self._vault_dns,
                    "api_version": VAULT_API_VERSION,
                    "object_count": len(objects),
                },
            }
        except Exception as e:
            return {"success": False, "message": str(e), "details": None}

    def list_objects(self) -> list[dict]:
        """List all Vault Objects."""
        self._ensure_connected()
        resp = self._request("GET", f"{self.base_url}/metadata/vobjects")
        objects = []
        for obj in resp.get("objects", []):
            objects.append(
                {
                    "name": obj.get("name", ""),
                    "label": obj.get("label", obj.get("name", "")),
                    "custom": obj.get("name", "").endswith("__v") is False,
                    "queryable": True,
                }
            )
        return objects

    def describe_object(self, object_name: str) -> SchemaObject:
        """Get field-level metadata for a Vault Object."""
        self._ensure_connected()
        resp = self._request(
            "GET", f"{self.base_url}/metadata/vobjects/{object_name}"
        )
        obj_info = resp.get("object", resp)
        fields_data = obj_info.get("fields", [])

        fields = []
        for f in fields_data:
            picklist_values = None
            if f.get("type") in ("Picklist", "picklist"):
                picklist_values = [
                    pv.get("value", pv.get("name", ""))
                    for pv in f.get("picklist_values", f.get("picklistValues", []))
                ]

            ref_to = None
            if f.get("type") in ("Object", "object", "ObjectReference"):
                ref_to = f.get("object", {}).get("name") if isinstance(f.get("object"), dict) else f.get("relationship_object")

            fields.append(
                SchemaField(
                    name=f.get("name", ""),
                    label=f.get("label", f.get("name", "")),
                    field_type=f.get("type", "unknown"),
                    is_required=f.get("required", False),
                    is_unique=f.get("unique", False),
                    length=f.get("max_length"),
                    picklist_values=picklist_values,
                    reference_to=ref_to,
                )
            )

        return SchemaObject(
            name=object_name,
            label=obj_info.get("label", object_name),
            fields=fields,
        )

    def get_record_count(self, object_name: str) -> int:
        """Get record count for a Vault Object using VQL."""
        self._ensure_connected()
        vql = f"SELECT id FROM {object_name} LIMIT 0"
        resp = self._request(
            "GET",
            f"{self.base_url}/query",
            params={"q": f"SELECT COUNT(id) FROM {object_name}"},
        )
        # Vault returns count in responseDetails or data
        if "responseDetails" in resp:
            return resp["responseDetails"].get("total", 0)
        if "data" in resp and resp["data"]:
            first = resp["data"][0]
            # COUNT queries return the count in the first field
            for v in first.values():
                if isinstance(v, int):
                    return v
        return 0

    def query_records(self, vql: str) -> list[dict]:
        """Execute a VQL query and return all records."""
        self._ensure_connected()
        all_records = []
        resp = self._request("GET", f"{self.base_url}/query", params={"q": vql})
        all_records.extend(resp.get("data", []))

        # Handle pagination
        while resp.get("responseDetails", {}).get("next_page"):
            next_url = resp["responseDetails"]["next_page"]
            if not next_url.startswith("http"):
                next_url = f"{self._vault_dns}{next_url}"
            resp = self._request("GET", next_url)
            all_records.extend(resp.get("data", []))

        return all_records

    def query_records_stream(
        self, object_name: str, fields: list[str]
    ) -> Generator[dict, None, None]:
        """Stream records from Vault using paginated VQL queries."""
        self._ensure_connected()
        field_str = ", ".join(fields)
        vql = f"SELECT {field_str} FROM {object_name}"

        resp = self._request("GET", f"{self.base_url}/query", params={"q": vql})
        for record in resp.get("data", []):
            yield record

        while resp.get("responseDetails", {}).get("next_page"):
            next_url = resp["responseDetails"]["next_page"]
            if not next_url.startswith("http"):
                next_url = f"{self._vault_dns}{next_url}"
            resp = self._request("GET", next_url)
            for record in resp.get("data", []):
                yield record

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """Make an authenticated request to the Vault API."""
        resp = self._client.request(method, url, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if data.get("responseStatus") == "FAILURE":
            errors = data.get("errors", [])
            msg = "; ".join(e.get("message", str(e)) for e in errors) if errors else "Unknown Vault error"
            raise RuntimeError(f"Vault API error: {msg}")
        return data

    def _ensure_connected(self):
        if self._client is None or self._session_id is None:
            self.connect()

    def close(self):
        if self._client:
            self._client.close()
