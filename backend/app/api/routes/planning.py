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
from app.models.connection import CHECKLIST as CHECKLIST_CONN_TYPE
from app.models.connection import GITHUB as GITHUB_CONN_TYPE
from app.models.connection import JIRA as JIRA_CONN_TYPE
from app.models.connection import SALESFORCE as SALESFORCE_CONN_TYPE
from app.models.connection import Connection
from app.models.plan import Plan as PlanModel
from app.models.plan import PlanStatus
from app.models.user import User
from app.schemas.plan import LayoutEdit
from app.schemas.plan import Plan as PlanSchema
from app.schemas.plan_schema import PLAN_JSON_SCHEMA
from app.schemas.planning import (
    ChecklistItemResult,
    CommitToGithubRequest,
    DeployPlanRequest,
    GatherContextRequest,
    GeneratePlanRequest,
    GithubCommitOut,
    JiraCommentOut,
    JiraImage,
    PlanningContext,
    PlanOut,
    PlanSummaryOut,
    PostTestPlanToJiraRequest,
    RefinePlanRequest,
    ReviewAgainstChecklistOut,
    ReviewAgainstChecklistRequest,
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
    filter_plan_for_deploy,
)
from app.services.checklist_review import review_plan_against_checklist
from app.services.layout_merge import resolve_layout_edit
from app.services.packager import build_repo_artifact
from app.services.target_detection import detect_target_objects
from app.services.planner import PlanGenerationError, generate_plan, refine_plan
from app.services.rag import retrieve_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/planning", tags=["planning"])

# Design-image upload constraints (e.g. Figma PNG/JPG exports).
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB per image (Anthropic API limit)
_MAX_IMAGES = 4
# Cap the number of layouts retrieved from the org to keep context manageable.
_MAX_LAYOUTS = 10


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
            images = data.pop("jira_images", []) or []
            for k, v in data.items():
                setattr(ctx, k, v)
            ctx.jira_images = [JiraImage.model_validate(i) for i in images]
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
        # Story text scopes the org pull to objects the ticket references, so we
        # describe the story's fields and retrieve its layouts rather than
        # scanning the whole org ("only what the story asks").
        story_text = " ".join(
            [
                ctx.jira_summary or "",
                ctx.jira_description or "",
                ctx.jira_acceptance_criteria or "",
            ]
        )
        try:
            sf = salesforce_from_connection(sf_conn)
            data = await asyncio.to_thread(
                sf.fetch_metadata, None, story_text or None
            )
            for k, v in data.items():
                setattr(ctx, k, v)

            # Retrieve existing Layout XML for the objects in scope so the
            # planner can automate layout changes (insert the field into the
            # real layout) instead of leaving them as a manual step. Scope the
            # pull to objects the story actually references so we don't retrieve
            # layouts for the entire org.
            try:
                objects = ctx.metadata_objects or []
                targets = detect_target_objects(story_text, objects)
                scope = targets or objects
                layout_names = await asyncio.to_thread(sf.list_layouts, scope)
                if layout_names:
                    ctx.existing_layouts = await asyncio.to_thread(
                        sf.fetch_layouts, layout_names[:_MAX_LAYOUTS]
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Layout retrieve failed: %s", exc)
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


def _resolve_layout_edits(plan_dict: dict, ctx: PlanningContext) -> dict:
    """Turn each step's declarative ``layout_edits`` into deployable layout files.

    Uses the org's existing layout XML (``ctx.existing_layouts``) so the emitted
    ``.layout`` preserves every required item (fixing the "must contain an item
    for required layout field: Name" deploy error). The merged file and its
    Layout package member are injected into the step's ``metadata_artifact``.

    If a layout's existing XML isn't available we leave the edit in place (it is
    surfaced to the developer) rather than fabricate a partial layout.
    """
    existing = ctx.existing_layouts or {}
    steps = plan_dict.get("steps")
    if not isinstance(steps, list):
        return plan_dict

    for step in steps:
        edits = step.get("layout_edits") or []
        if not edits:
            continue
        new_files: list[dict] = []
        new_members: list[dict] = []
        for edit in edits:
            try:
                le = LayoutEdit.model_validate(edit)
            except Exception:  # noqa: BLE001
                continue
            resolved = resolve_layout_edit(le, existing)
            if resolved is None:
                logger.warning(
                    "No existing XML for layout '%s'; cannot auto-merge. "
                    "Field placement left as a declared edit.",
                    le.layout_name,
                )
                continue
            path, xml = resolved
            new_files.append({"path": path, "body": xml})
            new_members.append({"type": "Layout", "name": le.layout_name})

        if not new_files:
            continue

        artifact = step.get("metadata_artifact")
        if not isinstance(artifact, dict):
            artifact = {"files": [], "members": [], "api_version": None}
        artifact.setdefault("files", [])
        artifact.setdefault("members", [])
        # Replace any prior layout files for the same paths (avoid duplicates).
        new_paths = {f["path"] for f in new_files}
        artifact["files"] = [
            f for f in artifact["files"] if f.get("path") not in new_paths
        ] + new_files
        existing_member_keys = {
            (m.get("type"), m.get("name")) for m in artifact["members"]
        }
        for m in new_members:
            if (m["type"], m["name"]) not in existing_member_keys:
                artifact["members"].append(m)
        step["metadata_artifact"] = artifact

    return plan_dict


def _unresolved_layout_names(plan_dict: dict) -> list[str]:
    """Layout fullNames declared in layout_edits that have no deployable file yet."""
    names: list[str] = []
    for step in plan_dict.get("steps") or []:
        edits = step.get("layout_edits") or []
        if not edits:
            continue
        artifact = step.get("metadata_artifact") or {}
        existing_paths = {
            f.get("path") for f in (artifact.get("files") or [])
        }
        for edit in edits:
            name = (edit or {}).get("layout_name")
            if not name:
                continue
            path = f"layouts/{name}.layout"
            if path not in existing_paths:
                names.append(name)
    # De-dup, preserve order.
    return list(dict.fromkeys(names))


def _resolve_layout_edits_live(plan_dict: dict, connector) -> tuple[dict, bool]:
    """Resolve unresolved layout_edits by fetching the target org's real layout.

    Returns ``(plan_dict, changed)``. Fetches only the layouts that still lack a
    deployable file, merges edits into that real XML (preserving required items),
    and injects the resulting files/members. Runs in a worker thread (blocking
    SF calls). No-op when everything is already resolved.
    """
    needed = _unresolved_layout_names(plan_dict)
    if not needed:
        return plan_dict, False

    object_names = list(
        dict.fromkeys(n.split("-", 1)[0] for n in needed if "-" in n)
    )
    connector.connect()
    # Prefer listing to validate the fullNames exist, but fetch by name directly.
    fetched = connector.fetch_layouts(needed) or {}
    if not fetched:
        # Fall back to listing by object then fetching, in case fullName casing
        # differs from what the plan declared.
        listed = connector.list_layouts(object_names) if object_names else []
        if listed:
            fetched = connector.fetch_layouts(listed) or {}
    if not fetched:
        logger.warning(
            "Could not retrieve layout XML for %s from target org; "
            "deploy may fail if the layout is required.",
            needed,
        )
        return plan_dict, False

    ctx = PlanningContext(existing_layouts=fetched)
    before = json.dumps(plan_dict, sort_keys=True)
    plan_dict = _resolve_layout_edits(plan_dict, ctx)
    changed = json.dumps(plan_dict, sort_keys=True) != before
    return plan_dict, changed


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

    # Feed JIRA-attached images to the planner alongside any manual uploads, so
    # a ticket's design attachments inform the plan even without a re-upload.
    jira_images = [
        ImageInput(media_type=img.media_type, data=img.data)
        for img in (ctx.jira_images or [])
        if img.data
    ]
    if jira_images:
        images = (images or []) + jira_images

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

    plan_dict = _resolve_layout_edits(plan_dict, ctx)

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


@router.post("/plans/{plan_id}/refine", response_model=PlanOut)
async def refine_existing_plan(
    plan_id: int,
    payload: RefinePlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    """Human-in-the-loop refinement: revise the same plan from reviewer feedback.

    The AI regenerates a refined version of the current plan incorporating the
    feedback, in place (same record). Refinement resets the lifecycle back to
    ``generated`` and clears any prior approval/deploy state, since the content
    has changed and must be re-reviewed. A plan already deploying cannot be
    refined.
    """
    feedback = (payload.feedback or "").strip()
    if not feedback:
        raise HTTPException(status_code=422, detail="Feedback must not be empty.")

    plan = await _owned_plan(db, user, plan_id)
    if plan.status == PlanStatus.DEPLOYING:
        raise HTTPException(
            status_code=409,
            detail="Cannot refine a plan while it is deploying.",
        )

    try:
        provider = get_llm_provider()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"LLM provider unavailable: {exc}")

    ctx = PlanningContext.model_validate(plan.context_snapshot or {})

    guide_context = ""
    query = " ".join(
        [ctx.jira_summary, ctx.jira_description, ctx.jira_acceptance_criteria]
    ).strip()
    try:
        guide_context = await retrieve_context(db, query or ctx.jira_ticket_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Guide retrieval failed: %s", exc)

    try:
        refined, refined_dict = await refine_plan(
            provider, ctx, plan.plan_json, feedback, guide_context
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

    refined_dict = _resolve_layout_edits(refined_dict, ctx)

    plan.summary = refined.summary
    plan.plan_json = refined_dict
    plan.provider = provider.name
    plan.model = getattr(provider, "_model", None)
    # Content changed -> require re-review; clear approval and deploy state.
    plan.status = PlanStatus.GENERATED
    plan.approved_at = None
    plan.approved_by_id = None
    plan.deploy_connection_id = None
    plan.deploy_async_id = None
    plan.deploy_started_at = None
    plan.deploy_finished_at = None
    plan.deploy_result = None
    await db.commit()
    await db.refresh(plan)
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

    connector = salesforce_from_connection(conn)

    # Safety net: ensure every declared layout_edit is resolved into a complete
    # layout file against the REAL layout in the TARGET org. This guarantees a
    # correct deploy even if the stored context lacked existing_layouts (e.g. an
    # older plan generated before layout XML was carried through), and it always
    # merges into the org we're deploying to. Persist any newly resolved files.
    try:
        plan_dict, changed = await asyncio.to_thread(
            _resolve_layout_edits_live, plan.plan_json, connector
        )
        if changed:
            plan.plan_json = plan_dict
            await db.commit()
            await db.refresh(plan)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live layout resolution before deploy failed: %s", exc)

    plan_schema = PlanSchema.model_validate(plan.plan_json)

    # Apply the reviewer's deploy-time selection (UI-only; not persisted). When
    # both are None this is a no-op and the full plan deploys.
    if payload.step_numbers is not None or payload.artifact_paths is not None:
        plan_schema = filter_plan_for_deploy(
            plan_schema,
            step_numbers=payload.step_numbers,
            artifact_paths=payload.artifact_paths,
        )

    # Fail fast with a clear message if there's nothing to deploy.
    try:
        build_package_zip(plan_schema)
    except NoDeployableMetadataError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                str(exc)
                if (payload.step_numbers is None and payload.artifact_paths is None)
                else "No deployable metadata in the selected steps/files."
            ),
        )

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


def _default_commit_branch(plan: PlanModel) -> str:
    ticket = (plan.jira_ticket or "plan").strip().replace(" ", "-")
    return f"ona/{ticket}-{plan.id}"


@router.post("/plans/{plan_id}/commit-github", response_model=GithubCommitOut)
async def commit_plan_to_github(
    plan_id: int,
    payload: CommitToGithubRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GithubCommitOut:
    """Commit an approved plan's metadata to a branch in a connected repo.

    An alternative to direct-org deploy: renders the plan's metadata in the
    repo's format (SFDX source by default, or MDAPI) and commits it to a new
    branch so the developer can review a diff and deploy from their pipeline.
    The plan must be approved first. Commits to a branch only — no PR is opened.
    """
    plan = await _owned_plan(db, user, plan_id)
    if plan.status not in (
        PlanStatus.APPROVED,
        PlanStatus.DEPLOYED,
        PlanStatus.DEPLOY_FAILED,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Approve the plan before committing to GitHub (current status "
                f"'{plan.status}'). Click Approve first."
            ),
        )

    conn = await _owned_conn(db, user, payload.github_connection_id)
    if conn.conn_type != GITHUB_CONN_TYPE:
        raise HTTPException(
            status_code=400,
            detail="commit target must be a GitHub connection.",
        )

    plan_schema = PlanSchema.model_validate(plan.plan_json)

    connector = github_from_connection(conn, payload.repo)

    # Format resolution: explicit request > connection setting > repo auto-detect.
    fmt = (payload.metadata_format or conn.config.get("metadata_format") or "").strip()
    if fmt not in ("sfdx", "mdapi"):
        try:
            detected = await connector.detect_format(payload.base_branch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub format detection failed: %s", exc)
            detected = "unknown"
        fmt = detected if detected in ("sfdx", "mdapi") else "sfdx"

    try:
        artifact = build_repo_artifact(plan_schema, fmt)
    except NoDeployableMetadataError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    branch = (payload.branch or "").strip() or _default_commit_branch(plan)
    message = (
        payload.commit_message
        or f"{plan.jira_ticket}: {plan.summary or 'ONA plan metadata'}"
    )

    try:
        result = await connector.commit_files(
            artifact.files,
            branch=branch,
            message=message,
            base_branch=payload.base_branch,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GitHub commit failed for plan %s", plan_id)
        raise HTTPException(status_code=502, detail=f"GitHub commit failed: {exc}")

    return GithubCommitOut(
        branch=result.branch,
        commit_sha=result.commit_sha,
        commit_url=result.commit_url,
        branch_url=result.branch_url,
        files=result.files,
        created_branch=result.created_branch,
        metadata_format=fmt,
    )


def _format_unit_test_plan_comment(plan: PlanModel) -> str:
    """Render the plan's unit test plan as a JIRA comment body (plain text)."""
    pj = plan.plan_json or {}
    tr = pj.get("testing_requirements") or {}
    lines = ["*ONA — Unit Test Plan*", ""]
    unit = (tr.get("unit_tests") or "").strip()
    lines.append(unit or "(No unit tests specified.)")

    functional = (tr.get("functional_tests") or "").strip()
    if functional:
        lines += ["", "*Functional tests*", functional]
    regression = (tr.get("regression_areas") or "").strip()
    if regression:
        lines += ["", "*Regression areas*", regression]
    coverage = tr.get("minimum_code_coverage")
    if coverage:
        lines += ["", f"Minimum code coverage: {coverage}%"]
    lines += ["", f"_Generated by ONA for plan {pj.get('plan_id', plan.id)}._"]
    return "\n".join(lines)


@router.post("/plans/{plan_id}/post-test-plan-jira", response_model=JiraCommentOut)
async def post_test_plan_to_jira(
    plan_id: int,
    payload: PostTestPlanToJiraRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JiraCommentOut:
    """Post the plan's unit test plan as a comment on the story.

    Writes the testing_requirements (unit tests + functional/regression/coverage)
    to the linked JIRA issue as a comment. Non-destructive; can be posted anytime
    after the plan is generated.
    """
    plan = await _owned_plan(db, user, plan_id)

    conn = await _owned_conn(db, user, payload.jira_connection_id)
    if conn.conn_type != JIRA_CONN_TYPE:
        raise HTTPException(
            status_code=400, detail="Select a JIRA connection to post the comment."
        )

    ticket_id = (payload.ticket_id or plan.jira_ticket or "").strip()
    if not ticket_id:
        raise HTTPException(
            status_code=422, detail="No JIRA ticket associated with this plan."
        )

    body = _format_unit_test_plan_comment(plan)
    try:
        result = await jira_from_connection(conn).add_comment(ticket_id, body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("JIRA comment failed for plan %s", plan_id)
        raise HTTPException(status_code=502, detail=f"JIRA comment failed: {exc}")

    return JiraCommentOut(
        ticket_id=ticket_id,
        comment_id=result.get("id"),
        url=result.get("url", ""),
    )


@router.post(
    "/plans/{plan_id}/review-checklist", response_model=ReviewAgainstChecklistOut
)
async def review_plan_checklist(
    plan_id: int,
    payload: ReviewAgainstChecklistRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewAgainstChecklistOut:
    """Review the plan against a checklist connection's rubric.

    Uses the LLM to judge each checklist item against the plan and returns a
    per-item pass/fail/partial result plus an overall verdict. Read-only.
    """
    plan = await _owned_plan(db, user, plan_id)

    conn = await _owned_conn(db, user, payload.checklist_connection_id)
    if conn.conn_type != CHECKLIST_CONN_TYPE:
        raise HTTPException(
            status_code=400, detail="Select a checklist connection to review against."
        )
    checklist_text = (conn.config or {}).get("content", "")
    if not checklist_text.strip():
        raise HTTPException(status_code=422, detail="Selected checklist is empty.")

    try:
        provider = get_llm_provider()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"LLM provider unavailable: {exc}")

    review = await review_plan_against_checklist(
        provider, plan.plan_json or {}, checklist_text
    )

    return ReviewAgainstChecklistOut(
        checklist_name=conn.name,
        overall=review["overall"],
        summary=review["summary"],
        results=[ChecklistItemResult(**r) for r in review["results"]],
    )
