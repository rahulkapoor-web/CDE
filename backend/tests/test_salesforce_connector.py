"""Tests for the OAuth2-based Salesforce connector.

These verify that authentication uses the REST token endpoint and never the
SOAP login() path, plus per-flow validation and backward-compatible flow
detection in salesforce_from_connection.
"""

import json

import pytest

from app.connectors.salesforce import SalesforceConnector


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Records the token request and returns a canned response."""

    last_url: str | None = None
    last_data: dict | None = None
    response = _FakeResponse(
        200,
        {
            "access_token": "TOKEN123",
            "instance_url": "https://acme.my.salesforce.com",
        },
    )

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, data=None, headers=None):
        type(self).last_url = url
        type(self).last_data = data
        return type(self).response


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    monkeypatch.setattr("app.connectors.salesforce.httpx.Client", _FakeClient)
    _FakeClient.last_url = None
    _FakeClient.last_data = None
    _FakeClient.response = _FakeResponse(
        200,
        {
            "access_token": "TOKEN123",
            "instance_url": "https://acme.my.salesforce.com",
        },
    )
    yield


@pytest.fixture(autouse=True)
def _patch_salesforce(monkeypatch):
    """Stub simple_salesforce.Salesforce so no network/SOAP call happens."""
    captured = {}

    class _FakeSF:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import simple_salesforce

    monkeypatch.setattr(simple_salesforce, "Salesforce", _FakeSF)
    return captured


def test_client_credentials_uses_my_domain_token_endpoint(_patch_salesforce):
    c = SalesforceConnector(
        auth_flow="client_credentials",
        client_id="cid",
        client_secret="csecret",
        instance_url="https://acme.my.salesforce.com",
    )
    c.connect()
    assert _FakeClient.last_url == (
        "https://acme.my.salesforce.com/services/oauth2/token"
    )
    assert _FakeClient.last_data["grant_type"] == "client_credentials"
    # Session handed to simple-salesforce, never SOAP login.
    assert _patch_salesforce["session_id"] == "TOKEN123"
    assert _patch_salesforce["instance_url"] == "https://acme.my.salesforce.com"
    assert "username" not in _patch_salesforce


def test_password_flow_uses_login_host_and_appends_token():
    c = SalesforceConnector(
        auth_flow="password",
        client_id="cid",
        client_secret="csecret",
        username="user@org.com",
        password="pw",
        security_token="tok",
    )
    c.connect()
    assert _FakeClient.last_url == (
        "https://login.salesforce.com/services/oauth2/token"
    )
    assert _FakeClient.last_data["grant_type"] == "password"
    assert _FakeClient.last_data["password"] == "pwtok"


def test_password_flow_prefers_my_domain_when_instance_url_set():
    c = SalesforceConnector(
        auth_flow="password",
        client_id="cid",
        client_secret="csecret",
        username="user@org.com",
        password="pw",
        instance_url="https://acme--dev.sandbox.my.salesforce.com",
    )
    c.connect()
    assert _FakeClient.last_url == (
        "https://acme--dev.sandbox.my.salesforce.com/services/oauth2/token"
    )


def test_password_flow_sandbox_uses_test_host():
    c = SalesforceConnector(
        auth_flow="password",
        client_id="cid",
        client_secret="csecret",
        username="user@org.com",
        password="pw",
        is_sandbox=True,
    )
    c.connect()
    assert _FakeClient.last_url == (
        "https://test.salesforce.com/services/oauth2/token"
    )


def test_jwt_bearer_builds_assertion(monkeypatch):
    monkeypatch.setattr(
        SalesforceConnector,
        "_build_jwt_assertion",
        lambda self: "SIGNED_JWT",
    )
    c = SalesforceConnector(
        auth_flow="jwt_bearer",
        client_id="cid",
        username="user@org.com",
        private_key="-----BEGIN PRIVATE KEY-----",
    )
    c.connect()
    assert _FakeClient.last_data["assertion"] == "SIGNED_JWT"
    assert (
        _FakeClient.last_data["grant_type"]
        == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    )


def test_access_token_flow_skips_token_call(_patch_salesforce):
    c = SalesforceConnector(
        auth_flow="access_token",
        access_token="PREOBTAINED",
        instance_url="https://acme.my.salesforce.com",
    )
    c.connect()
    assert _FakeClient.last_url is None  # no token request made
    assert _patch_salesforce["session_id"] == "PREOBTAINED"


@pytest.mark.parametrize(
    "kwargs,msg",
    [
        ({"auth_flow": "client_credentials", "client_id": "x"}, "client_credentials"),
        ({"auth_flow": "password", "client_id": "x"}, "password flow"),
        ({"auth_flow": "jwt_bearer", "client_id": "x"}, "jwt_bearer"),
        ({"auth_flow": "access_token"}, "access_token flow"),
    ],
)
def test_missing_fields_raise_value_error(kwargs, msg):
    c = SalesforceConnector(**kwargs)
    with pytest.raises(ValueError) as exc:
        c.connect()
    assert msg in str(exc.value)


def test_token_error_response_raises():
    _FakeClient.response = _FakeResponse(400, {"error": "invalid_client"})
    c = SalesforceConnector(
        auth_flow="client_credentials",
        client_id="cid",
        client_secret="csecret",
        instance_url="https://acme.my.salesforce.com",
    )
    with pytest.raises(ValueError) as exc:
        c.connect()
    assert "OAuth2 token request to" in str(exc.value)
    assert "failed (400)" in str(exc.value)


class _ObjDesc:
    def __init__(self, name: str):
        self._name = name

    def describe(self) -> dict:
        return {"fields": [{"name": "Name"}, {"name": f"{self._name}_Custom__c"}]}


class _MetaSF:
    """Fake Salesforce client capturing which objects get a field-describe."""

    def __init__(self, object_names: list[str]):
        self._object_names = object_names
        self.described: list[str] = []

    def describe(self) -> dict:
        return {
            "organizationType": "Developer Edition",
            "sobjects": [
                {"name": n, "custom": n.endswith("__c")} for n in self._object_names
            ],
        }

    def query_all(self, soql="", *_a, **_k):
        # Return names for the enablement SOQL helpers; empty otherwise.
        if "FROM Profile" in soql:
            return {"records": [{"Name": "System Administrator"}, {"Name": "Sales User"}]}
        if "FROM PermissionSet" in soql:
            return {"records": [{"Name": "PS_Sales"}, {"Name": "PS_Service"}]}
        return {"records": []}

    def __getattr__(self, item):
        # getattr(sf, obj).describe() path in fetch_metadata.
        if item in self._object_names:
            self.described.append(item)
            return _ObjDesc(item)
        raise AttributeError(item)


def _connector_with_fake(monkeypatch, fake) -> SalesforceConnector:
    c = SalesforceConnector(
        auth_flow="access_token",
        access_token="T",
        instance_url="https://acme.my.salesforce.com",
    )
    monkeypatch.setattr(c, "connect", lambda: fake)
    c.sf = fake
    return c


def test_fetch_metadata_focus_text_prioritizes_story_object(monkeypatch):
    # Many objects; the story references only the standard Account object, which
    # the default custom/LSC filter would NOT pick up. focus_text must pull it
    # into the described set so its fields are captured.
    names = ["Account", "Contact"] + [f"Filler{i}__c" for i in range(40)]
    fake = _MetaSF(names)
    c = _connector_with_fake(monkeypatch, fake)

    data = c.fetch_metadata(
        None, focus_text="Add Specialty field to the Account object"
    )

    # Account was described (its fields present) despite the 25-object cap.
    assert "Account" in fake.described
    assert any(f.startswith("Account.") for f in data["metadata_fields"])
    # Account is first in the scoped object ordering.
    assert data["metadata_objects"][0] == "Account"


def test_fetch_metadata_without_focus_uses_default_scope(monkeypatch):
    names = ["Account", "Custom_A__c", "Custom_B__c"]
    fake = _MetaSF(names)
    c = _connector_with_fake(monkeypatch, fake)

    data = c.fetch_metadata()

    # Default scope = custom objects only (standard Account excluded here).
    assert "Custom_A__c" in data["metadata_objects"]
    assert "Account" not in data["metadata_objects"]


def test_fetch_metadata_explicit_object_names_override_focus(monkeypatch):
    names = ["Account", "Contact", "Visit__c"]
    fake = _MetaSF(names)
    c = _connector_with_fake(monkeypatch, fake)

    data = c.fetch_metadata(["Contact"], focus_text="mentions Account only")

    # Explicit object_names win; focus_text is ignored when names are given.
    assert data["metadata_objects"] == ["Contact"]
    assert fake.described == ["Contact"]


def test_fetch_metadata_includes_profiles_and_permission_sets(monkeypatch):
    fake = _MetaSF(["Account", "Visit__c"])
    c = _connector_with_fake(monkeypatch, fake)

    data = c.fetch_metadata()

    # Profiles and permission sets populate the enablement selector.
    assert data["metadata_profiles"] == ["System Administrator", "Sales User"]
    assert data["metadata_permission_sets"] == ["PS_Sales", "PS_Service"]


class _VersionClient:
    """Stubs httpx.Client for the /services/data/ version discovery call."""

    payload: list = [
        {"version": "60.0"},
        {"version": "62.0"},
        {"version": "61.0"},
    ]
    status_code = 200

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers=None):
        _VersionClient.last_url = url
        return _VersionResponse(type(self).status_code, type(self).payload)


class _VersionResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_get_api_version_returns_highest_supported(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.salesforce.httpx.Client", _VersionClient
    )
    _VersionClient.status_code = 200
    _VersionClient.payload = [
        {"version": "60.0"},
        {"version": "62.0"},
        {"version": "61.0"},
    ]
    c = SalesforceConnector(
        auth_flow="access_token",
        access_token="T",
        instance_url="https://acme.my.salesforce.com",
    )

    # Numerically highest, not last-in-list, is chosen.
    assert c.get_api_version() == "62.0"
    assert _VersionClient.last_url.endswith("/services/data/")


def test_get_api_version_falls_back_on_error(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.salesforce.httpx.Client", _VersionClient
    )
    _VersionClient.status_code = 500
    c = SalesforceConnector(
        auth_flow="access_token",
        access_token="T",
        instance_url="https://acme.my.salesforce.com",
    )
    # On HTTP error it returns the safe default rather than raising.
    assert c.get_api_version() == "60.0"
