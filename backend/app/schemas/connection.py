from datetime import datetime
from pydantic import BaseModel


class ConnectionProfileCreate(BaseModel):
    name: str
    system_type: str  # "salesforce" or "veeva_vault"
    environment: str  # "sandbox" or "production"
    auth_method: str = "credentials"

    # Salesforce
    sf_instance_url: str | None = None
    sf_username: str | None = None
    sf_password: str | None = None
    sf_security_token: str | None = None
    sf_consumer_key: str | None = None
    sf_consumer_secret: str | None = None

    # Veeva Vault
    vault_dns: str | None = None
    vault_username: str | None = None
    vault_password: str | None = None


class ConnectionProfileUpdate(BaseModel):
    name: str | None = None
    environment: str | None = None
    auth_method: str | None = None
    sf_instance_url: str | None = None
    sf_username: str | None = None
    sf_password: str | None = None
    sf_security_token: str | None = None
    sf_consumer_key: str | None = None
    sf_consumer_secret: str | None = None
    vault_dns: str | None = None
    vault_username: str | None = None
    vault_password: str | None = None


class ConnectionProfileResponse(BaseModel):
    id: str
    name: str
    system_type: str
    environment: str
    auth_method: str
    sf_instance_url: str | None = None
    sf_username: str | None = None
    vault_dns: str | None = None
    vault_username: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    details: dict | None = None
