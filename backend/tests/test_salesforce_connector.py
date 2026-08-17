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
