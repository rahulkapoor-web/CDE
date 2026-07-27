"""Cleanup engine for removing migrated transactional data from Veeva Vault.

Deletes records in reverse hierarchy order (children first, parents last).
Supports two filter modes:
  - legacy_crm_id: delete records where legacy_crm_id__v IS NOT NULL
  - country: delete records related to accounts in a specific country
"""

import csv
import io
import logging
import os
from typing import Generator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.cleanup import CleanupJob
from app.models.connection import ConnectionProfile
from app.models.mapping import MigrationProject
from app.services.connector_factory import build_connector

logger = logging.getLogger(__name__)

# Object hierarchy from SOP migration steps CSV
# Step number defines the order — higher steps are children
HIERARCHY: list[dict] = []


def _load_hierarchy():
    """Load the object hierarchy from the SOP CSV file."""
    global HIERARCHY
    if HIERARCHY:
        return

    # Try project root first, then backend dir
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    csv_path = os.path.join(project_root, "SOP_migration_steps 1.csv")
    if not os.path.exists(csv_path):
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "SOP_migration_steps 1.csv",
        )
    if not os.path.exists(csv_path):
        logger.warning(f"Hierarchy CSV not found at {csv_path}, using hardcoded fallback")
        # Fallback hierarchy based on the known data
        HIERARCHY = [
            {"step": 8, "object": "question_response__v", "parents": "survey__v; survey_question__v; survey_target__v"},
            {"step": 7, "object": "medical_inquiry_fulfillment_response__v", "parents": "call2__v; medical_inquiry_fulfillment__v"},
            {"step": 6, "object": "call2_detail__v", "parents": "call2__v; product__v"},
            {"step": 6, "object": "call2_discussion__v", "parents": "call2__v"},
            {"step": 6, "object": "call2_key_message__v", "parents": "call2__v"},
            {"step": 6, "object": "call2_sample__v", "parents": "call2__v"},
            {"step": 6, "object": "action_item__v", "parents": "call2__v"},
            {"step": 6, "object": "call_objective__v", "parents": "call2__v"},
            {"step": 6, "object": "medical_insight__v", "parents": "call2__v"},
            {"step": 6, "object": "medical_inquiry_fulfillment__v", "parents": "call2__v"},
            {"step": 6, "object": "sample_limit_transaction__v", "parents": "call2__v"},
            {"step": 6, "object": "sent_email__v", "parents": "call2__v"},
            {"step": 5, "object": "call2__v", "parents": "account__v"},
            {"step": 5, "object": "medical_inquiry__v", "parents": "account__v"},
            {"step": 5, "object": "account_tactic__v", "parents": "account__v; account_plan__v"},
            {"step": 4, "object": "key_message__v", "parents": "product__v"},
            {"step": 4, "object": "key_stakeholder__v", "parents": "account__v"},
            {"step": 4, "object": "medical_event__v", "parents": "account__v"},
            {"step": 4, "object": "plan_tactic__v", "parents": "account_plan__v"},
            {"step": 4, "object": "product_metrics__v", "parents": "account__v"},
            {"step": 4, "object": "sample_limit__v", "parents": "account__v"},
            {"step": 4, "object": "swot__v", "parents": "account_plan__v"},
            {"step": 4, "object": "tsf__v", "parents": "account__v"},
            {"step": 4, "object": "account_team_member__v", "parents": "account_plan__v"},
            {"step": 3, "object": "time_off_territory__v", "parents": "user__sys; territory__v"},
            {"step": 3, "object": "account_territory__v", "parents": "account__v; territory__v"},
            {"step": 2, "object": "account_plan__v", "parents": "account__v"},
            {"step": 2, "object": "address__v", "parents": "account__v"},
            {"step": 2, "object": "affiliation__v", "parents": "account__v"},
            {"step": 2, "object": "child_account__v", "parents": "account__v"},
        ]
        return

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                step = int(row.get("Step", 0))
            except (ValueError, TypeError):
                continue
            obj = row.get("Object Name", "").strip()
            parents = row.get("Parent object", "").strip()
            team = row.get("Designated team", "").strip()
            if obj:
                HIERARCHY.append({
                    "step": step,
                    "object": obj,
                    "parents": parents,
                    "team": team,
                })

    # Sort by step descending (children first)
    HIERARCHY.sort(key=lambda x: x["step"], reverse=True)
    logger.info(f"Loaded {len(HIERARCHY)} objects in cleanup hierarchy")


def get_cleanup_order() -> list[dict]:
    """Return objects in deletion order (children first)."""
    _load_hierarchy()
    return HIERARCHY


async def execute_cleanup(cleanup_job_id: str):
    """Execute the cleanup job in a background thread."""
    from app.core.database import create_background_session

    _load_hierarchy()

    bg_session = create_background_session()
    async with bg_session() as db:
        job = await db.get(CleanupJob, cleanup_job_id)
        if not job:
            return

        job.status = "running"
        job.current_phase = "initializing"
        job.started_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await db.commit()

        try:
            project = await db.get(MigrationProject, job.project_id)
            target_profile = await db.get(ConnectionProfile, project.target_connection_id)
            connector = build_connector(target_profile)

            # Filter: only transactional objects (skip master data like account__v, user__sys, territory__v, product__v)
            master_data_objects = {
                "account__v", "user__sys", "territory__v", "product__v",
                "user_role__sys", "user_territory__v",
            }
            cleanup_objects = [
                h for h in HIERARCHY
                if h["object"] not in master_data_objects
                and h["step"] >= 2  # Skip step 1 (master data)
            ]

            job.total_steps = len(cleanup_objects)
            job.completed_steps = 0
            job.step_results = {}
            await db.commit()

            total_found = 0
            total_deleted = 0

            for i, obj_info in enumerate(cleanup_objects):
                # Check for cancellation
                await db.refresh(job)
                if job.status == "cancelled":
                    return

                obj_name = obj_info["object"]
                job.current_object = obj_name
                job.current_phase = "querying"
                await db.commit()

                try:
                    # Build VQL to find records to delete
                    if job.filter_mode == "legacy_crm_id":
                        vql = f"SELECT id FROM {obj_name} WHERE legacy_crm_id__v != ''"
                    elif job.filter_mode == "country":
                        # For objects directly linked to account, filter by account's country
                        # For deeper children (e.g., call2_detail linked to call2), we need
                        # to find parent call2 IDs first, then filter children
                        vql = _build_country_vql(obj_name, obj_info, job.country_code, connector)
                    else:
                        vql = f"SELECT id FROM {obj_name} WHERE legacy_crm_id__v != ''"

                    logger.info(f"Cleanup querying {obj_name}: {vql[:200]}")

                    # Fetch record IDs
                    records = connector.query_records(vql)
                    if records and len(records) > 0:
                        logger.info(f"Cleanup {obj_name} sample record keys: {list(records[0].keys())[:10]}")
                        logger.info(f"Cleanup {obj_name} sample record: {records[0]}")
                    record_ids = [r.get("id") for r in records if r.get("id")]
                    obj_found = len(record_ids)
                    logger.info(f"Cleanup {obj_name}: {len(records)} records returned, {obj_found} with 'id' field")
                    total_found += obj_found

                    job.records_found = total_found
                    job.current_phase = "deleting"
                    await db.commit()

                    # Delete in batches
                    obj_deleted = 0
                    obj_failed = 0
                    obj_errors = []

                    if record_ids:
                        result = connector.delete_records(obj_name, record_ids)
                        obj_deleted = result["success"]
                        obj_failed = result["failed"]
                        obj_errors = result.get("errors", [])
                        total_deleted += obj_deleted

                    job.records_deleted = total_deleted
                    sr = dict(job.step_results or {})
                    sr[obj_name] = {
                        "step": obj_info["step"],
                        "found": obj_found,
                        "deleted": obj_deleted,
                        "failed": obj_failed,
                        "errors": obj_errors[:5],
                    }
                    job.step_results = sr
                    flag_modified(job, "step_results")
                    job.completed_steps = i + 1
                    await db.commit()

                    logger.info(
                        f"Cleanup {obj_name}: found={obj_found}, deleted={obj_deleted}, failed={obj_failed}"
                    )

                except Exception as e:
                    err_msg = str(e)[:300]
                    logger.warning(f"Cleanup error for {obj_name}: {err_msg}")
                    sr = dict(job.step_results or {})
                    sr[obj_name] = {
                        "step": obj_info["step"],
                        "found": 0,
                        "deleted": 0,
                        "failed": 0,
                        "errors": [err_msg],
                        "skipped": True,
                    }
                    job.step_results = sr
                    flag_modified(job, "step_results")
                    job.completed_steps = i + 1
                    await db.commit()

            from datetime import datetime, timezone
            job.status = "completed"
            job.current_object = None
            job.current_phase = "done"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        except Exception as e:
            from datetime import datetime, timezone
            job.status = "failed"
            job.error_message = str(e)[:500]
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()


def _build_country_vql(
    obj_name: str, obj_info: dict, country_code: str, connector
) -> str:
    """Build VQL to find records related to accounts in a specific country.

    For objects directly linked to account__v, filter by account's country.
    For deeper children, traverse up through parent relationships.
    """
    parents = obj_info.get("parents", "")

    # Objects directly linked to account__v
    if "account__v" in parents:
        return (
            f"SELECT id FROM {obj_name} "
            f"WHERE account__v IN "
            f"(SELECT id FROM account__v WHERE country_code__v = '{country_code}')"
        )

    # Objects linked through call2__v (which links to account__v)
    if "call2__v" in parents:
        return (
            f"SELECT id FROM {obj_name} "
            f"WHERE call2__v IN "
            f"(SELECT id FROM call2__v WHERE account__v IN "
            f"(SELECT id FROM account__v WHERE country_code__v = '{country_code}'))"
        )

    # Objects linked through medical_inquiry__v → account__v
    if "medical_inquiry__v" in parents:
        return (
            f"SELECT id FROM {obj_name} "
            f"WHERE medical_inquiry__v IN "
            f"(SELECT id FROM medical_inquiry__v WHERE account__v IN "
            f"(SELECT id FROM account__v WHERE country_code__v = '{country_code}'))"
        )

    # Objects linked through account_plan__v → account__v
    if "account_plan__v" in parents:
        return (
            f"SELECT id FROM {obj_name} "
            f"WHERE account_plan__v IN "
            f"(SELECT id FROM account_plan__v WHERE account__v IN "
            f"(SELECT id FROM account__v WHERE country_code__v = '{country_code}'))"
        )

    # Fallback: use legacy_crm_id filter
    logger.warning(
        f"No country filter path for {obj_name} (parents: {parents}), "
        f"falling back to legacy_crm_id filter"
    )
    return f"SELECT id FROM {obj_name} WHERE legacy_crm_id__v != ''"
