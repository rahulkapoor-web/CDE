"""Backward-compatible auth-flow detection in salesforce_from_connection."""

import pytest

from app.models.connection import Connection
from app.services.connections import encrypt_secrets, salesforce_from_connection


def _conn(config: dict, secrets: dict | None = None) -> Connection:
    return Connection(
        user_id=1,
        name="sf",
        conn_type="salesforce",
        config=config,
        secrets_encrypted=encrypt_secrets(secrets or {}),
    )


@pytest.mark.parametrize(
    "config,secrets,expected",
    [
        # Explicit auth_flow always wins.
        ({"auth_flow": "jwt_bearer"}, {}, "jwt_bearer"),
        # client_id + secret + username -> password
        (
            {"client_id": "cid", "username": "u@o.com"},
            {"client_secret": "s"},
            "password",
        ),
        # client_id + secret, no username -> client_credentials
        ({"client_id": "cid"}, {"client_secret": "s"}, "client_credentials"),
        # access_token + instance_url -> access_token
        (
            {"instance_url": "https://acme.my.salesforce.com"},
            {"access_token": "t"},
            "access_token",
        ),
        # client_id + private_key -> jwt_bearer
        ({"client_id": "cid"}, {"private_key": "pem"}, "jwt_bearer"),
        # legacy username-only -> password (surfaces clear OAuth error later)
        ({"username": "u@o.com"}, {}, "password"),
        # nothing -> client_credentials default
        ({}, {}, "client_credentials"),
    ],
)
def test_flow_detection(config, secrets, expected):
    conn = _conn(config, secrets)
    connector = salesforce_from_connection(conn)
    assert connector.auth_flow == expected
