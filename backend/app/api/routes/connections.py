from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import encrypt_value
from app.api.deps import get_current_user
from app.models.user import User
from app.models.connection import ConnectionProfile
from app.schemas.connection import (
    ConnectionProfileCreate,
    ConnectionProfileUpdate,
    ConnectionProfileResponse,
    ConnectionTestResult,
)
from app.services.connector_factory import build_connector

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionProfileResponse])
async def list_connections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ConnectionProfile).where(ConnectionProfile.user_id == user.id)
    )
    return result.scalars().all()


@router.post("", response_model=ConnectionProfileResponse)
async def create_connection(
    data: ConnectionProfileCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = ConnectionProfile(
        user_id=user.id,
        name=data.name,
        system_type=data.system_type,
        environment=data.environment,
        auth_method=data.auth_method,
        sf_instance_url=data.sf_instance_url,
        sf_username=data.sf_username,
        sf_password_encrypted=encrypt_value(data.sf_password) if data.sf_password else None,
        sf_security_token_encrypted=encrypt_value(data.sf_security_token) if data.sf_security_token else None,
        sf_consumer_key=data.sf_consumer_key,
        sf_consumer_secret_encrypted=encrypt_value(data.sf_consumer_secret) if data.sf_consumer_secret else None,
        vault_dns=data.vault_dns,
        vault_username=data.vault_username,
        vault_password_encrypted=encrypt_value(data.vault_password) if data.vault_password else None,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{connection_id}", response_model=ConnectionProfileResponse)
async def get_connection(
    connection_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ConnectionProfile, connection_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return profile


@router.put("/{connection_id}", response_model=ConnectionProfileResponse)
async def update_connection(
    connection_id: str,
    data: ConnectionProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ConnectionProfile, connection_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    update_data = data.model_dump(exclude_unset=True)
    # Encrypt sensitive fields
    sensitive_map = {
        "sf_password": "sf_password_encrypted",
        "sf_security_token": "sf_security_token_encrypted",
        "sf_consumer_secret": "sf_consumer_secret_encrypted",
        "vault_password": "vault_password_encrypted",
    }
    for plain_key, enc_key in sensitive_map.items():
        if plain_key in update_data:
            val = update_data.pop(plain_key)
            if val:
                update_data[enc_key] = encrypt_value(val)

    for key, value in update_data.items():
        setattr(profile, key, value)

    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ConnectionProfile, connection_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(profile)
    await db.commit()
    return {"detail": "Deleted"}


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
async def test_connection(
    connection_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ConnectionProfile, connection_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Connection not found")

    connector = build_connector(profile)
    result = connector.test_connection()
    return ConnectionTestResult(**result)
