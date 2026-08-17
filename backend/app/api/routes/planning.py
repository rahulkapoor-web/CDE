"""Context gathering and plan generation/history routes."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.connectors.sfdx import parse_sfdx_project
from app.core.database import get_db
from app.llm.factory import get_llm_provider
from app.models.connection import Connection
from app.models.plan import Plan as PlanModel
from app.models.user import User
from app.schemas.plan_schema import PLAN_JSON_SCHEMA
from app.schemas.planning import (
    GatherContextRequest,
    GeneratePlanRequest,
    PlanningContext,
    PlanOut,
    PlanSummaryOut,
)
from app.services.connections import (
    github_from_connection,
    jira_from_connection,
    salesforce_from_connection,
)
from app.services.planner import PlanGenerationError, generate_plan
from app.services.rag import retrieve_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/planning", tags=["planning"])


async def _owned_conn(db, user, conn_id: int | None) -> Connection | None:
    if conn_id is None:
        return None
    result = await db.execute(
        select(Connection).where(
            Connection.id == conn_id, Connection.user_id == user.id
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {conn_id} not found")
    return conn


@router.get("/schema")
async def get_schema() -> dict:
    """Expose the canonical plan JSON schema."""
    return PLAN_JSON_SCHEMA


@router.post("/context", response_model=PlanningContext)
async def gather_context(
    payload: GatherContextRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanningContext:
    """Gather context from live integrations and/or SFDX. All fields editable."""
    ctx = PlanningContext()

    jira_conn = await _owned_conn(db, user, payload.jira_connection_id)
    if jira_conn and payload.jira_ticket_id:
        try:
            data = await jira_from_connection(jira_conn).fetch_ticket(
                payload.jira_ticket_id
            )
            for k, v in data.items():
                setattr(ctx, k, v)
        except Exception as exc:  # noqa: BLE001
            logger.warning("JIRA fetch failed: %s", exc)
            ctx.jira_ticket_id = payload.jira_ticket_id
    elif payload.jira_ticket_id:
        ctx.jira_ticket_id = payload.jira_ticket_id

    gh_conn = await _owned_conn(db, user, payload.github_connection_id)
    if gh_conn:
        try:
            data = await github_from_connection(
                gh_conn, payload.github_repo
            ).fetch_state(payload.github_branch)
            for k, v in data.items():
                setattr(ctx, k, v)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub fetch failed: %s", exc)

    sf_conn = await _owned_conn(db, user, payload.salesforce_connection_id)
    if sf_conn:
        try:
            data = await asyncio.to_thread(
                salesforce_from_connection(sf_conn).fetch_metadata
            )
            for k, v in data.items():
                setattr(ctx, k, v)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Salesforce metadata fetch failed: %s", exc)

    if payload.sfdx_path:
        try:
            data = parse_sfdx_project(payload.sfdx_path)
            # Merge SFDX metadata into any existing snapshot.
            for k, v in data.items():
                current = getattr(ctx, k, None)
                if isinstance(v, list) and isinstance(current, list):
                    merged = list(dict.fromkeys(current + v))
                    setattr(ctx, k, merged)
                elif v:
                    setattr(ctx, k, v)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SFDX parse failed: %s", exc)

    return ctx


@router.post("/generate", response_model=PlanOut)
async def generate(
    payload: GeneratePlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    ctx = payload.context
    try:
        provider = get_llm_provider()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"LLM provider unavailable: {exc}")

    query = " ".join(
        [ctx.jira_summary, ctx.jira_description, ctx.jira_acceptance_criteria]
    ).strip()
    guide_context = ""
    try:
        guide_context = await retrieve_context(db, query or ctx.jira_ticket_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Guide retrieval failed: %s", exc)

    try:
        plan, plan_dict = await generate_plan(provider, ctx, guide_context)
    except PlanGenerationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "attempts": exc.attempts,
                "errors": exc.last_errors,
            },
        )

    record = PlanModel(
        user_id=user.id,
        jira_ticket=plan.jira_ticket,
        summary=plan.summary,
        status="generated",
        provider=provider.name,
        model=getattr(provider, "_model", None),
        context_snapshot=ctx.model_dump(),
        plan_json=plan_dict,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return PlanOut.model_validate(record)


@router.get("/plans", response_model=list[PlanSummaryOut])
async def list_plans(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PlanModel)
        .where(PlanModel.user_id == user.id)
        .order_by(PlanModel.created_at.desc())
    )
    return [PlanSummaryOut.model_validate(p) for p in result.scalars().all()]


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PlanModel).where(
            PlanModel.id == plan_id, PlanModel.user_id == user.id
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return PlanOut.model_validate(plan)
