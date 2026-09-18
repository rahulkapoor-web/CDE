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

    Handles: whitespace, case for text, date formats, None/empty,
    list/array unwrapping (Vault picklists return single-element arrays).
    """
    if value is None:
        return None
    # Unwrap single-element lists (Vault picklist values come as arrays)
    if isinstance(value, list):
        if len(value) == 0:
            return None
        if len(value) == 1:
            value = value[0]
        else:
            # Multi-value: sort and join for consistent comparison
            return ";".join(sorted(str(v).strip().lower() for v in value))
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        # Normalize numeric: strip trailing zeros
        return f"{float(value):.6f}".rstrip("0").rstrip(".")

    s = str(value).strip()
    if not s:
        return None

    # Detect stringified lists like "['submitted__v']"
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
        # Remove surrounding quotes
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            s = s[1:-1].strip()
        if not s:
            return None

    # Try date normalization — either when field_type hints at it,
    # or when the value looks like a date/datetime string
    parsed_date = _try_parse_date(s, field_type)
    if parsed_date is not None:
        return parsed_date

    # General text: lowercase, collapse whitespace
    s = re.sub(r"\s+", " ", s).lower()
    return s


# Regex to detect date-like strings: 2025-09-10, 2025-09-10T14:05:10...
_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}"  # starts with YYYY-MM-DD
)

# Formats to try, ordered from most specific to least
_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f%z",   # 2025-09-10T14:05:10.000+0000
    "%Y-%m-%dT%H:%M:%S.%fZ",    # 2025-09-10T14:05:10.000Z
    "%Y-%m-%dT%H:%M:%S%z",      # 2025-09-10T14:05:10+0000
    "%Y-%m-%dT%H:%M:%SZ",       # 2025-09-10T14:05:10Z
    "%Y-%m-%dT%H:%M:%S",        # 2025-09-10T14:05:10
    "%Y-%m-%d",                  # 2025-09-10
]


def _try_parse_date(s: str, field_type: str = "") -> str | None:
    """Try to parse a string as a date/datetime.

    Returns a normalized date string if successful, None otherwise.
    Detects dates by field_type hint or by matching date-like patterns.
    """
    ft_lower = field_type.lower()
    is_date_field = ft_lower in ("date", "datetime", "date/time")

    # Only attempt parsing if field type says date OR value looks like a date
    if not is_date_field and not _DATE_PATTERN.match(s):
        return None

    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            # If the value is date-only (no time component in the string),
            # normalize to date only
            if "T" not in s:
                return dt.strftime("%Y-%m-%d")
            # For datetime values, normalize to second precision without timezone
            # This makes 2025-09-10T14:05:10.000+0000 == 2025-09-10T14:05:10.000Z
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue

    return None


def _values_equivalent(src_val: str | None, tgt_val: str | None) -> bool:
    """Check if two normalized values are semantically equivalent.

    Handles cross-system differences:
      - null/empty vs 0: null ≈ 0 (empty numeric defaults)
      - 0/1 vs false/true: numeric booleans
      - 'Submitted' vs 'submitted_v': Vault API name suffixes (__v, __c)
      - 'Some Value' vs 'some_value__v': snake_case API names
    """
    if src_val is None and tgt_val is None:
        return True
    if src_val == tgt_val:
        return True

    # null vs 0 — treat as equivalent
    zero_vals = {"0", "0.0", "0.00"}
    if src_val is None and tgt_val in zero_vals:
        return True
    if tgt_val is None and src_val in zero_vals:
        return True

    # 0/1 vs false/true
    bool_map = {"0": "false", "1": "true", "0.0": "false", "1.0": "true"}
    if src_val in bool_map and tgt_val == bool_map[src_val]:
        return True
    if tgt_val in bool_map and src_val == bool_map[tgt_val]:
        return True

    # Strip Vault suffixes (__v, __c, __sys, _v, _c) and compare
    if src_val is not None and tgt_val is not None:
        src_clean = re.sub(r"(__v|__c|__sys|_v|_c)$", "", src_val)
        tgt_clean = re.sub(r"(__v|__c|__sys|_v|_c)$", "", tgt_val)

        # Direct match after stripping suffixes
        if src_clean == tgt_clean:
            return True

        # snake_case vs human-readable: "submitted" vs "submitted",
        # "some value" vs "some_value"
        src_snake = src_clean.replace(" ", "_").replace("-", "_")
        tgt_snake = tgt_clean.replace(" ", "_").replace("-", "_")
        if src_snake == tgt_snake:
            return True

    return False


def _is_id_or_reference(source_type: str, target_type: str) -> bool:
    """Check if a field mapping represents an ID or reference/lookup field.

    These fields will always differ between Salesforce and Vault because
    each system generates its own IDs.
    """
    src = (source_type or "").lower()
    tgt = (target_type or "").lower()

    id_indicators = ("id", "reference", "lookup", "record type")
    tgt_id_indicators = ("id", "object")

    if any(src.startswith(ind) or src == ind for ind in id_indicators):
        return True
    if tgt in tgt_id_indicators:
        return True
    return False


def _dates_match(src_val: str | None, tgt_val: str | None) -> bool:
    """Check if two normalized values represent the same date.

    Handles cases like datetime vs date-only:
      '2025-09-16T22:00:00' vs '2025-09-16' → True (same date)
    """
    if src_val is None or tgt_val is None:
        return False
    # Both must look like dates
    if not _DATE_PATTERN.match(src_val) or not _DATE_PATTERN.match(tgt_val):
        return False
    # Extract date portion (first 10 chars: YYYY-MM-DD)
    return src_val[:10] == tgt_val[:10]


async def _rewrite_where_for_child(
    db: AsyncSession,
    where_clause: str,
    object_mapping,
    field_mappings: list,
) -> str:
    """Rewrite a WHERE clause for child objects by adding parent relationship prefix.

    If the WHERE clause references a field (e.g., OCE__Account__c) that doesn't exist
    directly on this object but exists on a parent object reachable via a lookup field,
    rewrite it to use the relationship path (e.g., OCE__Call__r.OCE__Account__c).
    """
    # Extract field names referenced in the WHERE clause
    # Match patterns like: field_name IN (...) or field_name = '...'
    referenced_fields = set(re.findall(r"(\w+__c)\s*(?:in|=|!=|<|>|like)", where_clause, re.IGNORECASE))

    if not referenced_fields:
        return where_clause

    # Get all fields on this object (from field mappings)
    object_fields = {fm.source_field for fm in field_mappings}

    # Find fields in WHERE that are NOT on this object
    missing_fields = referenced_fields - object_fields

    if not missing_fields:
        return where_clause  # All fields exist on this object, no rewrite needed

    # Find lookup fields on this object that could be parent relationships.
    # Exclude system lookups (CreatedById, LastModifiedById, OwnerId) — these
    # point to User, not to the business parent object.
    system_lookups = {"createdbyid", "lastmodifiedbyid", "ownerid", "userrecordaccessid"}
    lookup_fields = [
        fm for fm in field_mappings
        if fm.source_field_type and "lookup" in fm.source_field_type.lower()
        and fm.source_field.endswith("__c")
        and fm.source_field.lower() not in system_lookups
    ]

    if not lookup_fields:
        return where_clause

    # For each missing field, find the best parent lookup to prefix with.
    # Prefer lookups whose name shares a prefix with the object name
    # (e.g., OCE__Call__c for OCE__CallEmployeeAttendee__c)
    for missing_field in missing_fields:
        best_lookup = None
        for lookup in lookup_fields:
            # Check if the lookup type hints at the parent having this field
            lookup_type = (lookup.source_field_type or "").lower()
            if "account" in lookup_type and "account" in missing_field.lower():
                best_lookup = lookup
                break
            if "interaction" in lookup_type or "call" in lookup.source_field.lower():
                best_lookup = lookup
                # Don't break — keep looking for a more specific match

        if not best_lookup:
            best_lookup = lookup_fields[0]  # Fallback to first non-system lookup

        # Convert lookup field name to relationship name: OCE__Call__c -> OCE__Call__r
        rel_name = best_lookup.source_field[:-1] + "r"
        where_clause = re.sub(
            rf"\b{re.escape(missing_field)}\b",
            f"{rel_name}.{missing_field}",
            where_clause,
        )
        logger.info(
            f"Rewrote WHERE for {object_mapping.source_object}: "
            f"{missing_field} -> {rel_name}.{missing_field}"
        )

    return where_clause


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
        logger.warning(
            f"No match keys configured for {object_mapping.source_object} -> {object_mapping.target_object}, skipping"
        )
        # Create a skipped summary instead of failing the entire run
        summary = ValidationSummary(
            validation_run_id=validation_run.id,
            object_mapping_id=object_mapping.id,
            source_object=object_mapping.source_object,
            target_object=object_mapping.target_object,
            status="skipped",
            error_message="No match keys configured — skipped",
        )
        db.add(summary)
        await db.flush()
        return summary

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

            # For child objects, rewrite field references to use parent relationship.
            # e.g., if WHERE clause has OCE__Account__c and this object has a lookup
            # field OCE__Call__c pointing to the parent, rewrite to OCE__Call__r.OCE__Account__c
            cw = await _rewrite_where_for_child(
                db, cw, object_mapping, field_mappings
            )

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

                is_ref = _is_id_or_reference(
                    fm.source_field_type or "", fm.target_field_type or ""
                )

                if src_val == tgt_val:
                    entry["diff_type"] = "match"
                elif _dates_match(src_val, tgt_val):
                    entry["diff_type"] = "match"
                elif _values_equivalent(src_val, tgt_val):
                    entry["diff_type"] = "match"
                elif is_ref:
                    # ID/reference fields always differ between systems — not a mismatch
                    entry["diff_type"] = "id_reference"
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

            # Record is always "matched" if found in target.
            # Field-level diffs are warnings, not record-level failures.
            matched += 1
            if has_mismatch:
                mismatched += 1  # track for summary stats, but record status stays "matched"
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
