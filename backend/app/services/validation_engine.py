"""Validation engine for record-by-record comparison between source and target.

Handles both real-time (small datasets) and chunked processing (large datasets).
Normalizes values before comparison to handle type/format differences.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.mapping import ObjectMapping, FieldMapping, MatchKeyConfig
from app.models.validation import ValidationRun, ValidationSummary, ValidationDetail
from app.services.connector_factory import build_connector
from app.models.connection import ConnectionProfile

logger = logging.getLogger(__name__)


def _normalize_value(value: Any, field_type: str = "") -> str | None:
    """Normalize a field value for comparison.

    Handles: whitespace, case for text, date formats, None/empty.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        # Normalize numeric: strip trailing zeros
        return f"{float(value):.6f}".rstrip("0").rstrip(".")

    s = str(value).strip()
    if not s:
        return None

    # Normalize dates: try to parse ISO formats
    ft_lower = field_type.lower()
    if ft_lower in ("date", "datetime"):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                dt = datetime.strptime(s, fmt)
                if ft_lower == "date":
                    return dt.strftime("%Y-%m-%d")
                return dt.strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue

    # General text: lowercase, collapse whitespace
    s = re.sub(r"\s+", " ", s).lower()
    return s


def _build_match_key(record: dict, key_fields: list[str]) -> str:
    """Build a composite match key from one or more fields."""
    parts = []
    for f in key_fields:
        val = record.get(f)
        parts.append(str(val).strip().lower() if val is not None else "")
    return "||".join(parts)


async def run_validation_for_object(
    db: AsyncSession,
    validation_run: ValidationRun,
    object_mapping: ObjectMapping,
    source_profile: ConnectionProfile,
    target_profile: ConnectionProfile,
) -> ValidationSummary:
    """Run full record-by-record validation for a single object mapping."""

    # Load field mappings and match keys
    field_mappings_result = await db.execute(
        select(FieldMapping).where(FieldMapping.object_mapping_id == object_mapping.id)
    )
    field_mappings = list(field_mappings_result.scalars().all())

    match_keys_result = await db.execute(
        select(MatchKeyConfig)
        .where(MatchKeyConfig.object_mapping_id == object_mapping.id)
        .order_by(MatchKeyConfig.key_order)
    )
    match_keys = list(match_keys_result.scalars().all())

    if not match_keys:
        raise ValueError(
            f"No match keys configured for {object_mapping.source_object} -> {object_mapping.target_object}"
        )

    # Create summary record
    summary = ValidationSummary(
        validation_run_id=validation_run.id,
        object_mapping_id=object_mapping.id,
        source_object=object_mapping.source_object,
        target_object=object_mapping.target_object,
        status="running",
    )
    db.add(summary)
    await db.flush()

    try:
        source_connector = build_connector(source_profile)
        target_connector = build_connector(target_profile)

        # Determine fields to query
        source_key_fields = [mk.source_field for mk in match_keys]
        target_key_fields = [mk.target_field for mk in match_keys]
        source_data_fields = [fm.source_field for fm in field_mappings]
        target_data_fields = [fm.target_field for fm in field_mappings]

        all_source_fields = list(set(source_key_fields + source_data_fields))
        all_target_fields = list(set(target_key_fields + target_data_fields))

        # Fetch source records and index by match key
        logger.info(f"Fetching source records from {object_mapping.source_object}")
        source_index: dict[str, dict] = {}
        if hasattr(source_connector, "bulk_query"):
            for record in source_connector.bulk_query(object_mapping.source_object, all_source_fields):
                key = _build_match_key(record, source_key_fields)
                source_index[key] = record
        else:
            field_str = ", ".join(all_source_fields)
            records = source_connector.query_records(f"SELECT {field_str} FROM {object_mapping.source_object}")
            for record in records:
                key = _build_match_key(record, source_key_fields)
                source_index[key] = record

        # Fetch target records and index by match key
        logger.info(f"Fetching target records from {object_mapping.target_object}")
        target_index: dict[str, dict] = {}
        if hasattr(target_connector, "query_records_stream"):
            for record in target_connector.query_records_stream(object_mapping.target_object, all_target_fields):
                key = _build_match_key(record, target_key_fields)
                target_index[key] = record
        else:
            records = target_connector.query_records(
                f"SELECT {', '.join(all_target_fields)} FROM {object_mapping.target_object}"
            )
            for record in records:
                key = _build_match_key(record, target_key_fields)
                target_index[key] = record

        # Compare
        source_count = len(source_index)
        target_count = len(target_index)
        matched = 0
        mismatched = 0
        missing_in_target = 0
        missing_in_source = 0
        details_to_add: list[ValidationDetail] = []

        # Check source records against target
        for key, src_record in source_index.items():
            if key not in target_index:
                missing_in_target += 1
                details_to_add.append(
                    ValidationDetail(
                        summary_id=summary.id,
                        match_key_value=key,
                        status="missing_in_target",
                    )
                )
                continue

            tgt_record = target_index[key]
            diffs = {}
            for fm in field_mappings:
                src_val = _normalize_value(
                    src_record.get(fm.source_field), fm.source_field_type or ""
                )
                tgt_val = _normalize_value(
                    tgt_record.get(fm.target_field), fm.target_field_type or ""
                )
                if src_val != tgt_val:
                    diffs[fm.source_field] = {
                        "source": src_record.get(fm.source_field),
                        "target": tgt_record.get(fm.target_field),
                        "source_field": fm.source_field,
                        "target_field": fm.target_field,
                    }

            if diffs:
                mismatched += 1
                details_to_add.append(
                    ValidationDetail(
                        summary_id=summary.id,
                        match_key_value=key,
                        status="mismatched",
                        field_diffs=diffs,
                    )
                )
            else:
                matched += 1

        # Check for records in target but not in source
        for key in target_index:
            if key not in source_index:
                missing_in_source += 1
                details_to_add.append(
                    ValidationDetail(
                        summary_id=summary.id,
                        match_key_value=key,
                        status="missing_in_source",
                    )
                )

        # Batch insert details
        for detail in details_to_add:
            db.add(detail)

        # Update summary
        summary.source_count = source_count
        summary.target_count = target_count
        summary.matched_count = matched
        summary.mismatched_count = mismatched
        summary.missing_in_target_count = missing_in_target
        summary.missing_in_source_count = missing_in_source
        summary.match_percentage = (matched / source_count * 100) if source_count > 0 else 0.0
        summary.status = "completed"

        await db.flush()
        logger.info(
            f"Validation complete for {object_mapping.source_object}: "
            f"{matched} matched, {mismatched} mismatched, "
            f"{missing_in_target} missing in target, {missing_in_source} extra in target"
        )

    except Exception as e:
        summary.status = "failed"
        summary.error_message = str(e)
        await db.flush()
        logger.error(f"Validation failed for {object_mapping.source_object}: {e}")

    return summary
