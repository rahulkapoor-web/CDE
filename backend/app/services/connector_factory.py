"""Factory to instantiate the right connector from a ConnectionProfile."""

from app.connectors.salesforce import SalesforceConnector
from app.connectors.veeva_vault import VeevaVaultConnector
from app.core.security import decrypt_value
from app.models.connection import ConnectionProfile


def build_salesforce_connector(profile: ConnectionProfile) -> SalesforceConnector:
    return SalesforceConnector(
        username=profile.sf_username,
        password=decrypt_value(profile.sf_password_encrypted) if profile.sf_password_encrypted else None,
        security_token=decrypt_value(profile.sf_security_token_encrypted) if profile.sf_security_token_encrypted else None,
        instance_url=profile.sf_instance_url,
        consumer_key=profile.sf_consumer_key,
        consumer_secret=decrypt_value(profile.sf_consumer_secret_encrypted) if profile.sf_consumer_secret_encrypted else None,
        access_token=decrypt_value(profile.oauth_access_token_encrypted) if profile.oauth_access_token_encrypted else None,
        is_sandbox=profile.environment == "sandbox",
    )


def build_vault_connector(profile: ConnectionProfile) -> VeevaVaultConnector:
    return VeevaVaultConnector(
        vault_dns=profile.vault_dns,
        username=profile.vault_username,
        password=decrypt_value(profile.vault_password_encrypted) if profile.vault_password_encrypted else None,
        session_id=decrypt_value(profile.oauth_access_token_encrypted) if profile.oauth_access_token_encrypted else None,
    )


def build_connector(profile: ConnectionProfile):
    if profile.system_type == "salesforce":
        return build_salesforce_connector(profile)
    elif profile.system_type == "veeva_vault":
        return build_vault_connector(profile)
    else:
        raise ValueError(f"Unknown system type: {profile.system_type}")
