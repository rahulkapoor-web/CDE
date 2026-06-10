"""Auto-mapping engine that suggests field mappings between source and target schemas.

Uses fuzzy name matching, label matching, and type compatibility scoring.
"""

import re
from thefuzz import fuzz

from app.schemas.mapping import SchemaField, AutoMappingSuggestion

# Type compatibility matrix: source_type -> set of compatible target types
TYPE_COMPAT = {
    "string": {"String", "Text", "LongText", "string", "text"},
    "textarea": {"String", "Text", "LongText", "string", "text", "textarea"},
    "id": {"String", "ID", "string", "id", "ObjectReference"},
    "reference": {"ObjectReference", "Object", "reference", "string"},
    "boolean": {"YesNo", "Boolean", "boolean", "Checkbox"},
    "double": {"Number", "Currency", "double", "number"},
    "currency": {"Number", "Currency", "double", "currency"},
    "int": {"Number", "number", "int"},
    "date": {"Date", "date"},
    "datetime": {"DateTime", "datetime"},
    "email": {"String", "email", "Email"},
    "phone": {"String", "phone", "Phone"},
    "url": {"String", "url", "URL"},
    "picklist": {"Picklist", "picklist"},
    "multipicklist": {"Picklist", "multipicklist", "MultiPicklist"},
    "percent": {"Number", "percent", "Percent"},
}


def _normalize_name(name: str) -> str:
    """Strip namespace prefixes and suffixes for comparison.

    Salesforce: Namespace__FieldName__c -> FieldName
    Vault: field_name__v -> field_name
    """
    # Remove Salesforce custom suffix
    name = re.sub(r"__c$", "", name)
    # Remove Vault suffix
    name = re.sub(r"__v$", "", name)
    # Remove namespace prefix (e.g., OCEP__ or iqvia__)
    name = re.sub(r"^[A-Za-z0-9]+__", "", name)
    return name.lower().replace("_", "")


def _type_compatible(source_type: str, target_type: str) -> bool:
    source_lower = source_type.lower()
    target_lower = target_type.lower()
    if source_lower == target_lower:
        return True
    compatible = TYPE_COMPAT.get(source_lower, set())
    return target_type in compatible or target_lower in {t.lower() for t in compatible}


def suggest_field_mappings(
    source_fields: list[SchemaField],
    target_fields: list[SchemaField],
    threshold: float = 0.6,
) -> list[AutoMappingSuggestion]:
    """Generate mapping suggestions between source and target fields.

    Scoring:
    - Exact normalized name match: 1.0
    - Fuzzy name match (>80): 0.7-0.95
    - Label match (>80): 0.5-0.8
    - Type compatibility bonus: +0.1
    - Type incompatibility penalty: -0.2
    """
    suggestions: list[AutoMappingSuggestion] = []
    used_targets: set[str] = set()

    # Build scored pairs
    scored_pairs: list[tuple[float, str, SchemaField, SchemaField]] = []

    for sf in source_fields:
        src_norm = _normalize_name(sf.name)
        for tf in target_fields:
            tgt_norm = _normalize_name(tf.name)

            # Name-based scoring
            if src_norm == tgt_norm:
                score = 1.0
                reason = "exact name match"
            else:
                name_ratio = fuzz.ratio(src_norm, tgt_norm) / 100.0
                label_ratio = fuzz.ratio(sf.label.lower(), tf.label.lower()) / 100.0
                token_ratio = fuzz.token_sort_ratio(src_norm, tgt_norm) / 100.0

                best_ratio = max(name_ratio, label_ratio, token_ratio)
                if best_ratio < 0.5:
                    continue

                score = best_ratio * 0.9
                if best_ratio == label_ratio:
                    reason = f"label similarity ({label_ratio:.0%})"
                elif best_ratio == token_ratio:
                    reason = f"token similarity ({token_ratio:.0%})"
                else:
                    reason = f"name similarity ({name_ratio:.0%})"

            # Type compatibility adjustment
            if _type_compatible(sf.field_type, tf.field_type):
                score = min(score + 0.1, 1.0)
                reason += " + type compatible"
            else:
                score -= 0.2
                reason += " (type mismatch)"

            if score >= threshold:
                scored_pairs.append((score, reason, sf, tf))

    # Greedy assignment: highest score first, each target used once
    scored_pairs.sort(key=lambda x: x[0], reverse=True)
    used_sources: set[str] = set()

    for score, reason, sf, tf in scored_pairs:
        if sf.name in used_sources or tf.name in used_targets:
            continue
        used_sources.add(sf.name)
        used_targets.add(tf.name)
        suggestions.append(
            AutoMappingSuggestion(
                source_field=sf.name,
                target_field=tf.name,
                source_field_type=sf.field_type,
                target_field_type=tf.field_type,
                confidence_score=round(score, 3),
                match_reason=reason,
            )
        )

    suggestions.sort(key=lambda s: s.confidence_score, reverse=True)
    return suggestions
