from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ConnType = Literal["jira", "github", "salesforce"]


class ConnectionCreate(BaseModel):
    name: str
    conn_type: ConnType
    config: dict = {}
    # Secret values provided by the client; never stored in plaintext.
    secrets: dict = {}


class ConnectionUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    secrets: dict | None = None


class ConnectionOut(BaseModel):
    id: int
    name: str
    conn_type: ConnType
    config: dict
    has_secrets: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConnectionTestResult(BaseModel):
    ok: bool
    detail: str
    info: dict = {}
