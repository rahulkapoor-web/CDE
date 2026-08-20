"""Context gathering and plan generation/history routes."""

import asyncio
import base64
import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.connectors.sfdx import parse_sfdx_project
from app.core.database import get_db
from app.llm.base import ImageInput
from app.llm.factory import get_llm_provider
from app.models.connection import SALESFORCE as SALESFORCE_CONN_TYPE
from app.models.connection import Connection
from app.models.plan import Plan as PlanModel
from app.models.plan import PlanStatus
from app.models.user import User
from app.schemas.plan import Plan as PlanSchema
from app.schemas.plan_schema import PLAN_JSON_SCHEMA
from app.schemas.planning import (
    DeployPlanRequest,
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
from app.services.deployer import (
    NoDeployableMetadataError,
    build_package_zip,
    deploy_plan,
)
from app.services.planner import PlanGenerationError, generate_plan
from app.services.rag import retrieve_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/planning", tags=["planning"])

# Design-image upload constraints (e.g. Figma PNG/JPG exports).
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB per image (Anthropic API limit)
_MAX_IMAGES = 4


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


async def _run_generation(
    db: AsyncSession,
    user: User,
    ctx: PlanningContext,
    images: list[ImageInput] | None = None,
) -> PlanOut:
    """Shared plan-generation pipeline for JSON and multipart entrypoints."""
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
        plan, plan_dict = await generate_plan(
            provider, ctx, guide_context, images=images
        )
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


async def _read_image_uploads(files: list[UploadFile]) -> list[ImageInput]:
    """Validate and base64-encode uploaded design images."""
    if len(files) > _MAX_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"At most {_MAX_IMAGES} images may be uploaded.",
        )
    images: list[ImageInput] = []
    for f in files:
        if f.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported image type '{f.content_type}'. Allowed: "
                    + ", ".join(sorted(_ALLOWED_IMAGE_TYPES))
                ),
            )
        data = await f.read()
        if len(data) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Image '{f.filename}' exceeds the 5 MB limit.",
            )
        if not data:
            continue
        images.append(
            ImageInput(
                media_type=f.content_type,
                data=base64.b64encode(data).decode("ascii"),
            )
        )
    return images


@router.post("/generate", response_model=PlanOut)
async def generate(
    payload: GeneratePlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    return await _run_generation(db, user, payload.context)


@router.post("/generate-with-images", response_model=PlanOut)
async def generate_with_images(
    context: str = Form(..., description="JSON-encoded PlanningContext"),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    """Generate a plan with optional design images (e.g. Figma exports).

    ``context`` is the JSON-serialized PlanningContext; ``files`` are image
    uploads sent as multipart/form-data.
    """
    try:
        ctx = PlanningContext.model_validate(json.loads(context))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid context: {exc}")

    images = await _read_image_uploads(files)
    return await _run_generation(db, user, ctx, images=images or None)


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


async def _owned_plan(db, user, plan_id: int) -> PlanModel:
    result = await db.execute(
        select(PlanModel).where(
            PlanModel.id == plan_id, PlanModel.user_id == user.id
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await _owned_plan(db, user, plan_id)
    return PlanOut.model_validate(plan)


@router.post("/plans/{plan_id}/approve", response_model=PlanOut)
async def approve_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Developer review gate: mark a generated plan approved for deployment.

    No org changes happen here. Only a ``generated`` plan can be approved; an
    already-approved or deployed plan is returned unchanged (idempotent for the
    approved state).
    """
    plan = await _owned_plan(db, user, plan_id)
    if plan.status in (
        PlanStatus.APPROVED,
        PlanStatus.DEPLOYING,
        PlanStatus.DEPLOYED,
    ):
        return PlanOut.model_validate(plan)
    if plan.status != PlanStatus.GENERATED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve a plan in status '{plan.status}'.",
        )
    plan.status = PlanStatus.APPROVED
    plan.approved_at = func.now()
    plan.approved_by_id = user.id
    await db.commit()
    await db.refresh(plan)
    return PlanOut.model_validate(plan)


@router.post("/plans/{plan_id}/deploy", response_model=PlanOut)
async def deploy_approved_plan(
    plan_id: int,
    payload: DeployPlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply an approved plan's metadata to a connected Salesforce org.

    Requires the plan to be approved first ("Go ahead"). Deploys the merged
    Metadata API package built from each step's ``metadata_artifact`` via the
    Metadata API. Set ``check_only`` for a validation-only dry run.
    """
    plan = await _owned_plan(db, user, plan_id)

    if payload.check_only:
        # Dry runs are allowed from approved state without changing lifecycle.
        if plan.status not in (
            PlanStatus.APPROVED,
            PlanStatus.DEPLOYED,
            PlanStatus.DEPLOY_FAILED,
        ):
            raise HTTPException(
                status_code=409,
                detail="Approve the plan before running a validation deploy.",
            )
    elif plan.status not in (PlanStatus.APPROVED, PlanStatus.DEPLOY_FAILED):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Plan must be approved before deploying (current status "
                f"'{plan.status}'). Click Approve first."
            ),
        )

    conn = await _owned_conn(db, user, payload.salesforce_connection_id)
    if conn.conn_type != SALESFORCE_CONN_TYPE:
        raise HTTPException(
            status_code=400,
            detail="deploy target must be a Salesforce connection.",
        )

    plan_schema = PlanSchema.model_validate(plan.plan_json)

    # Fail fast with a clear message if there's nothing to deploy.
    try:
        build_package_zip(plan_schema)
    except NoDeployableMetadataError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    connector = salesforce_from_connection(conn)

    if not payload.check_only:
        plan.status = PlanStatus.DEPLOYING
        plan.deploy_connection_id = conn.id
        plan.deploy_started_at = func.now()
        plan.deploy_result = None
        plan.deploy_async_id = None
        await db.commit()
        await db.refresh(plan)

    def _run() -> tuple[str, dict]:
        sf = connector.connect()
        return deploy_plan(
            sf,
            plan_schema,
            is_sandbox=connector.is_sandbox,
            check_only=payload.check_only,
        )

    try:
        async_id, status = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Deploy failed for plan %s", plan_id)
        if not payload.check_only:
            plan.status = PlanStatus.DEPLOY_FAILED
            plan.deploy_finished_at = func.now()
            plan.deploy_result = {"succeeded": False, "error": str(exc)}
            await db.commit()
            await db.refresh(plan)
        raise HTTPException(status_code=502, detail=f"Deployment error: {exc}")

    if payload.check_only:
        # Report the dry-run result without mutating lifecycle/persisted state.
        out = PlanOut.model_validate(plan)
        out.deploy_result = {**status, "check_only": True}
        return out

    plan.deploy_async_id = async_id
    plan.deploy_finished_at = func.now()
    plan.deploy_result = status
    plan.status = (
        PlanStatus.DEPLOYED if status.get("succeeded") else PlanStatus.DEPLOY_FAILED
    )
    await db.commit()
    await db.refresh(plan)
    return PlanOut.model_validate(plan)
