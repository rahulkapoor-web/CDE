"""Connection CRUD and test endpoints for JIRA, GitHub, Salesforce."""

import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.connection import Connection
from app.models.user import User
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionTestResult,
    ConnectionUpdate,
)
from app.services.connections import (
    encrypt_secrets,
    github_from_connection,
    jira_from_connection,
    salesforce_from_connection,
)

router = APIRouter(prefix="/connections", tags=["connections"])


def _to_out(conn: Connection) -> ConnectionOut:
    return ConnectionOut(
        id=conn.id,
        name=conn.name,
        conn_type=conn.conn_type,
        config=conn.config or {},
        has_secrets=bool(conn.secrets_encrypted),
        created_at=conn.created_at,
    )


@router.get("", response_model=list[ConnectionOut])
async def list_connections(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Connection).where(Connection.user_id == user.id).order_by(Connection.id)
    )
    return [_to_out(c) for c in result.scalars().all()]


@router.post("", response_model=ConnectionOut, status_code=201)
async def create_connection(
    payload: ConnectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = Connection(
        user_id=user.id,
        name=payload.name,
        conn_type=payload.conn_type,
        config=payload.config,
        secrets_encrypted=encrypt_secrets(payload.secrets),
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _to_out(conn)


async def _get_owned(db: AsyncSession, user: User, conn_id: int) -> Connection:
    result = await db.execute(
        select(Connection).where(
            Connection.id == conn_id, Connection.user_id == user.id
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.patch("/{conn_id}", response_model=ConnectionOut)
async def update_connection(
    conn_id: int,
    payload: ConnectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await _get_owned(db, user, conn_id)
    if payload.name is not None:
        conn.name = payload.name
    if payload.config is not None:
        conn.config = payload.config
    if payload.secrets is not None:
        conn.secrets_encrypted = encrypt_secrets(payload.secrets)
    await db.commit()
    await db.refresh(conn)
    return _to_out(conn)


@router.delete("/{conn_id}", status_code=204)
async def delete_connection(
    conn_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await _get_owned(db, user, conn_id)
    await db.delete(conn)
    await db.commit()


@router.post("/{conn_id}/test", response_model=ConnectionTestResult)
async def test_connection(
    conn_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await _get_owned(db, user, conn_id)
    try:
        if conn.conn_type == "jira":
            info = await jira_from_connection(conn).test()
        elif conn.conn_type == "github":
            info = await github_from_connection(conn).test()
        elif conn.conn_type == "salesforce":
            # simple-salesforce is sync; run in a thread.
            info = await asyncio.to_thread(salesforce_from_connection(conn).test)
        else:
            raise HTTPException(status_code=400, detail="Unknown connection type")
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        return ConnectionTestResult(
            ok=False, detail=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        )
    except Exception as exc:  # noqa: BLE001
        return ConnectionTestResult(ok=False, detail=str(exc))
    return ConnectionTestResult(ok=True, detail="Connection successful", info=info)
