"""Validation engine for record-by-record comparison between source and target.

Handles both real-time (small datasets) and chunked processing (large datasets).
Normalizes values before comparison to handle type/format differences.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
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

        # Validate fields against actual schema to avoid query errors
        try:
            source_schema = source_connector.describe_object(object_mapping.source_object)
            valid_source_names = {f.name for f in source_schema.fields}
            invalid_source = [f for f in all_source_fields if f not in valid_source_names]
            if invalid_source:
                logger.warning(
                    f"Skipping {len(invalid_source)} invalid source fields: {invalid_source}"
                )
                all_source_fields = [f for f in all_source_fields if f in valid_source_names]
                # Also filter field_mappings so comparison doesn't reference missing data
                field_mappings = [
                    fm for fm in field_mappings if fm.source_field in valid_source_names
                ]
        except Exception:
            pass  # If describe fails, proceed and let the query error surface naturally

        try:
            target_schema = target_connector.describe_object(object_mapping.target_object)
            valid_target_names = {f.name for f in target_schema.fields}
            invalid_target = [f for f in all_target_fields if f not in valid_target_names]
            if invalid_target:
                logger.warning(
                    f"Skipping {len(invalid_target)} invalid target fields: {invalid_target}"
                )
                all_target_fields = [f for f in all_target_fields if f in valid_target_names]
                field_mappings = [
                    fm for fm in field_mappings if fm.target_field in valid_target_names
                ]
        except Exception:
            pass

        # Update phase: fetching source
        validation_run.progress_phase = "fetching_source"
        validation_run.source_records_fetched = 0
        validation_run.target_records_fetched = 0
        validation_run.records_compared = 0
        validation_run.total_records_to_compare = 0
        await db.commit()

        # Helper: flush record counter to DB every N records
        PROGRESS_FLUSH_INTERVAL = 200

        # Record limit and date range for sampling mode
        record_limit = validation_run.record_limit
        date_range_months = validation_run.date_range_months
        limit_clause = f" LIMIT {record_limit}" if record_limit else ""

        # Build WHERE clause for source query
        where_parts = []
        if date_range_months:
            cutoff = datetime.now(timezone.utc) - relativedelta(months=date_range_months)
            sf_cutoff = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
            where_parts.append(f"CreatedDate >= {sf_cutoff}")

        custom_where = validation_run.source_where_clause
        if custom_where:
            # Strip leading WHERE if user included it
            cw = custom_where.strip()
            if cw.upper().startswith("WHERE "):
                cw = cw[6:]
            where_parts.append(f"({cw})")

        source_where = ""
        if where_parts:
            source_where = " WHERE " + " AND ".join(where_parts)

        filter_desc = ""
        if date_range_months:
            filter_desc += f", last {date_range_months} months"
        if record_limit:
            filter_desc += f", limit {record_limit}"

        # Fetch source records and index by match key
        logger.info(f"Fetching source records from {object_mapping.source_object}{filter_desc}")
        source_index: dict[str, dict] = {}
        src_fetch_count = 0

        def _source_limit_reached():
            return record_limit and src_fetch_count >= record_limit

        # Use query_records with full SOQL when filters are present;
        # only use bulk_query when fetching everything with no filters
        use_bulk = (
            hasattr(source_connector, "bulk_query")
            and not source_where
            and not limit_clause
        )

        if use_bulk:
            for record in source_connector.bulk_query(object_mapping.source_object, all_source_fields):
                if _source_limit_reached():
                    break
                key = _build_match_key(record, source_key_fields)
                source_index[key] = record
                src_fetch_count += 1
                if src_fetch_count % PROGRESS_FLUSH_INTERVAL == 0:
                    validation_run.source_records_fetched = src_fetch_count
                    await db.commit()
        else:
            field_str = ", ".join(all_source_fields)
            soql = f"SELECT {field_str} FROM {object_mapping.source_object}{source_where}{limit_clause}"
            logger.info(f"Source SOQL: {soql[:200]}")
            records = source_connector.query_records(soql)
            for record in records:
                if _source_limit_reached():
                    break
                key = _build_match_key(record, source_key_fields)
                source_index[key] = record
                src_fetch_count += 1
                if src_fetch_count % PROGRESS_FLUSH_INTERVAL == 0:
                    validation_run.source_records_fetched = src_fetch_count
                    await db.commit()

        validation_run.source_records_fetched = src_fetch_count
        await db.commit()

        # Update phase: fetching target
        validation_run.progress_phase = "fetching_target"
        await db.commit()

        # Fetch target records and index by match key
        logger.info(f"Fetching target records from {object_mapping.target_object}{filter_desc}")
        target_index: dict[str, dict] = {}
        tgt_fetch_count = 0

        def _target_limit_reached():
            return record_limit and tgt_fetch_count >= record_limit

        if hasattr(target_connector, "query_records_stream"):
            for record in target_connector.query_records_stream(object_mapping.target_object, all_target_fields):
                if _target_limit_reached():
                    break
                key = _build_match_key(record, target_key_fields)
                target_index[key] = record
                tgt_fetch_count += 1
                if tgt_fetch_count % PROGRESS_FLUSH_INTERVAL == 0:
                    validation_run.target_records_fetched = tgt_fetch_count
                    await db.commit()
        else:
            vql = f"SELECT {', '.join(all_target_fields)} FROM {object_mapping.target_object}{limit_clause}"
            records = target_connector.query_records(vql)
            for record in records:
                key = _build_match_key(record, target_key_fields)
                target_index[key] = record
                tgt_fetch_count += 1
                if tgt_fetch_count % PROGRESS_FLUSH_INTERVAL == 0:
                    validation_run.target_records_fetched = tgt_fetch_count
                    await db.commit()

        validation_run.target_records_fetched = tgt_fetch_count
        await db.commit()

        # Update phase: comparing records
        validation_run.progress_phase = "comparing"
        validation_run.total_records_to_compare = len(source_index)
        validation_run.records_compared = 0
        await db.commit()

        # Compare: only check source → target (is each source record in target?)
        source_count = len(source_index)
        target_count = len(target_index)
        matched = 0
        mismatched = 0
        missing_in_target = 0
        compared_count = 0
        details_to_add: list[ValidationDetail] = []

        for key, src_record in source_index.items():
            compared_count += 1
            if compared_count % PROGRESS_FLUSH_INTERVAL == 0:
                validation_run.records_compared = compared_count
                await db.commit()

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

            # Record found in target — build full field comparison
            tgt_record = target_index[key]
            field_details = {}
            has_mismatch = False

            for fm in field_mappings:
                src_raw = src_record.get(fm.source_field)
                tgt_raw = tgt_record.get(fm.target_field)
                src_val = _normalize_value(src_raw, fm.source_field_type or "")
                tgt_val = _normalize_value(tgt_raw, fm.target_field_type or "")

                entry = {
                    "source": src_raw,
                    "target": tgt_raw,
                    "source_field": fm.source_field,
                    "target_field": fm.target_field,
                }

                if src_val == tgt_val:
                    entry["diff_type"] = "match"
                elif src_val is not None and tgt_val is None:
                    entry["diff_type"] = "missing_attribute"
                    has_mismatch = True
                elif src_val is None and tgt_val is not None:
                    entry["diff_type"] = "extra_in_target"
                    has_mismatch = True
                else:
                    entry["diff_type"] = "value_mismatch"
                    has_mismatch = True

                field_details[fm.source_field] = entry

            if has_mismatch:
                mismatched += 1
                details_to_add.append(
                    ValidationDetail(
                        summary_id=summary.id,
                        match_key_value=key,
                        status="mismatched",
                        field_diffs=field_details,
                    )
                )
            else:
                matched += 1
                details_to_add.append(
                    ValidationDetail(
                        summary_id=summary.id,
                        match_key_value=key,
                        status="matched",
                        field_diffs=field_details,
                    )
                )

        validation_run.records_compared = compared_count

        # Batch insert details
        for detail in details_to_add:
            db.add(detail)

        summary.source_count = source_count
        summary.target_count = target_count
        summary.matched_count = matched
        summary.mismatched_count = mismatched
        summary.missing_in_target_count = missing_in_target
        summary.missing_in_source_count = 0
        summary.match_percentage = (matched / source_count * 100) if source_count > 0 else 0.0
        summary.status = "completed"

        await db.flush()
        logger.info(
            f"Validation complete for {object_mapping.source_object}: "
            f"{matched} matched, {mismatched} mismatched, "
            f"{missing_in_target} missing in target"
        )

    except Exception as e:
        summary.status = "failed"
        summary.error_message = str(e)
        await db.flush()
        logger.error(f"Validation failed for {object_mapping.source_object}: {e}")

    return summary
