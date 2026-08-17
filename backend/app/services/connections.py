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
    return SalesforceConnector(
        username=conn.config.get("username"),
        password=secrets.get("password"),
        security_token=secrets.get("security_token"),
        instance_url=conn.config.get("instance_url"),
        access_token=secrets.get("access_token"),
        is_sandbox=conn.config.get("is_sandbox", False),
    )
