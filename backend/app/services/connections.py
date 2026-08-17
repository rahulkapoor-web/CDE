"""Connection helpers: secret encryption and connector instantiation."""

import json

from app.connectors.github import GitHubConnector
from app.connectors.jira import JiraConnector
from app.connectors.salesforce import SalesforceConnector
from app.core.security import decrypt_secret, encrypt_secret
from app.models.connection import Connection


def encrypt_secrets(secrets: dict) -> str | None:
    if not secrets:
        return None
    return encrypt_secret(json.dumps(secrets))


def decrypt_secrets(conn: Connection) -> dict:
    if not conn.secrets_encrypted:
        return {}
    return json.loads(decrypt_secret(conn.secrets_encrypted))


def jira_from_connection(conn: Connection) -> JiraConnector:
    secrets = decrypt_secrets(conn)
    return JiraConnector(
        base_url=conn.config.get("base_url", ""),
        email=conn.config.get("email"),
        api_token=secrets.get("api_token", ""),
    )


def github_from_connection(conn: Connection, repo_override: str | None = None) -> GitHubConnector:
    secrets = decrypt_secrets(conn)
    return GitHubConnector(
        token=secrets.get("token", ""),
        repo=repo_override or conn.config.get("repo", ""),
    )


def salesforce_from_connection(conn: Connection) -> SalesforceConnector:
    secrets = decrypt_secrets(conn)
    config = conn.config or {}

    # Determine the auth flow, with backward-compatible auto-detection for
    # connections created before the auth_flow field existed.
    auth_flow = config.get("auth_flow")
    if not auth_flow:
        if config.get("client_id") and secrets.get("client_secret"):
            auth_flow = "password" if config.get("username") else "client_credentials"
        elif secrets.get("access_token") and config.get("instance_url"):
            auth_flow = "access_token"
        elif config.get("client_id") and secrets.get("private_key"):
            auth_flow = "jwt_bearer"
        else:
            # Legacy username/password — surfaces a clear OAuth error directing
            # the user to configure a Connected App.
            auth_flow = "password" if config.get("username") else "client_credentials"

    return SalesforceConnector(
        auth_flow=auth_flow,
        client_id=config.get("client_id"),
        client_secret=secrets.get("client_secret"),
        username=config.get("username"),
        password=secrets.get("password"),
        security_token=secrets.get("security_token"),
        private_key=secrets.get("private_key"),
        instance_url=config.get("instance_url"),
        access_token=secrets.get("access_token"),
        is_sandbox=config.get("is_sandbox", False),
    )
