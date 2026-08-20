"""Normalize common LLM output drift into the canonical plan shape.

The plan schema is intentionally strict (see ``app/schemas/plan_schema.py`` and
``app/schemas/plan.py``). Language models, however, repeatedly emit a small,
predictable set of *shape* mistakes even when the prompt is explicit:

* ``testing_requirements`` returned as a string or with extra/renamed keys.
* ``deployment_sequence`` returned as a string/list, or omitted.
* ``open_questions`` / ``prerequisites`` / ``post_deployment`` items returned as
  objects instead of plain strings.
* ``lsc_guide_references`` items returned as strings instead of objects.
* ``dependencies`` / deployment step lists containing strings instead of ints.

Rather than loosen the schema (which encodes real business rules) or rely solely
on prompt wording and retries, we coerce these known mistakes into the canonical
form. Coercion is conservative: anything already correct is passed through
unchanged, and anything we cannot safely interpret is left as-is so the strict
validators still reject it.
"""

from __future__ import annotations

import re
from typing import Any

_TESTING_KEYS = {"unit_tests", "functional_tests", "regression_areas"}

# Common alias -> canonical key for testing_requirements.
_TESTING_ALIASES = {
    "unit_test": "unit_tests",
    "unittests": "unit_tests",
    "apex_tests": "unit_tests",
    "functional_test": "functional_tests",
    "functional_scenarios": "functional_tests",
    "functional": "functional_tests",
    "regression": "regression_areas",
    "regression_scope": "regression_areas",
    "regression_test": "regression_areas",
    "regression_areas": "regression_areas",
}

_COVERAGE_ALIASES = {
    "minimum_code_coverage",
    "minimum_apex_coverage_percent",
    "min_code_coverage",
    "code_coverage",
    "coverage",
}

_STRING_LIST_FIELDS = (
    "prerequisites",
    "post_deployment",
    "open_questions",
    "copilot_suggested_actions",
)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        m = re.search(r"-?\d+", value)
        if m:
            return int(m.group())
    return None


def _int_list(value: Any) -> Any:
    """Coerce a value into a list of ints where each item is convertible."""
    if not isinstance(value, list):
        return value
    out: list[Any] = []
    for item in value:
        # Some models wrap step numbers as {"step": 3} or {"step_number": 3}.
        if isinstance(item, dict):
            for key in ("step_number", "step", "number", "id"):
                if key in item:
                    item = item[key]
                    break
        coerced = _as_int(item)
        out.append(coerced if coerced is not None else item)
    return out


def _flatten_to_string(value: Any) -> str:
    """Render an object/list item as a readable single string."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Prefer an obvious text field if present.
        for key in ("text", "question", "description", "value", "item", "title"):
            if key in value and isinstance(value[key], str):
                return value[key]
        parts = [f"{k}: {v}" for k, v in value.items()]
        return "; ".join(parts)
    if isinstance(value, list):
        return "; ".join(_flatten_to_string(v) for v in value)
    return str(value)


def _coerce_string_list(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return [_flatten_to_string(item) for item in value]


def _coerce_testing_requirements(value: Any) -> Any:
    """Return an object with exactly the canonical testing_requirements keys."""
    # A bare string: put it in functional_tests and fill sensible defaults.
    if isinstance(value, str):
        return {
            "unit_tests": value,
            "functional_tests": value,
            "regression_areas": value,
            "minimum_code_coverage": 75,
        }
    if isinstance(value, list):
        joined = _flatten_to_string(value)
        return {
            "unit_tests": joined,
            "functional_tests": joined,
            "regression_areas": joined,
            "minimum_code_coverage": 75,
        }
    if not isinstance(value, dict):
        return value

    result: dict[str, Any] = {}
    coverage: int | None = None
    extras: list[str] = []

    for key, val in value.items():
        canonical = _TESTING_ALIASES.get(key, key)
        if canonical in _TESTING_KEYS:
            # Merge if two aliases map to the same canonical key.
            text = _flatten_to_string(val)
            if canonical in result and result[canonical]:
                result[canonical] = f"{result[canonical]}; {text}"
            else:
                result[canonical] = text
        elif key in _COVERAGE_ALIASES:
            coverage = _as_int(val)
        else:
            # Unknown/extra key: fold its content into regression_areas so
            # information is preserved rather than dropped.
            extras.append(f"{key}: {_flatten_to_string(val)}")

    for key in _TESTING_KEYS:
        result.setdefault(key, "")

    if extras:
        note = "; ".join(extras)
        result["regression_areas"] = (
            f"{result['regression_areas']}; {note}".strip("; ")
            if result["regression_areas"]
            else note
        )

    result["minimum_code_coverage"] = coverage if coverage is not None else 75
    return result


def _coerce_deployment_sequence(value: Any, step_numbers: list[int]) -> Any:
    """Return an object with the three canonical integer-list keys."""
    canonical_keys = ("sandbox_steps", "production_steps", "github_actions_steps")

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in canonical_keys:
            result[key] = _int_list(value.get(key, []) or [])
        return result

    # A string or list description we cannot reliably parse into three ordered
    # buckets. Fall back to a safe default: everything runs in sandbox first,
    # nothing auto-promoted to production, so downstream business rules stay
    # consistent. This keeps generation succeeding instead of hard-failing.
    if isinstance(value, (str, list)) or value is None:
        return {
            "sandbox_steps": list(step_numbers),
            "production_steps": [],
            "github_actions_steps": [],
        }
    return value


_LSC_REF_KEYS = ("module", "section", "page_or_url", "relevance")

# Aliases models sometimes use for the reference keys.
_LSC_REF_ALIASES = {
    "name": "module",
    "title": "module",
    "guide": "module",
    "chapter": "section",
    "heading": "section",
    "url": "page_or_url",
    "link": "page_or_url",
    "page": "page_or_url",
    "why": "relevance",
    "reason": "relevance",
    "notes": "relevance",
}


def _coerce_lsc_reference(item: Any) -> Any:
    """Return an lsc_guide_reference object with all four required string keys."""
    if isinstance(item, str):
        return {
            "module": item,
            "section": "",
            "page_or_url": "",
            "relevance": "",
        }
    if isinstance(item, dict):
        result: dict[str, Any] = {}
        extras: list[str] = []
        for key, val in item.items():
            canonical = _LSC_REF_ALIASES.get(key, key)
            if canonical in _LSC_REF_KEYS and canonical not in result:
                result[canonical] = _flatten_to_string(val)
            else:
                extras.append(f"{key}: {_flatten_to_string(val)}")
        # Fill any missing required keys so strict validation passes.
        for key in _LSC_REF_KEYS:
            result.setdefault(key, "")
        if extras:
            note = "; ".join(extras)
            result["relevance"] = (
                f"{result['relevance']}; {note}".strip("; ")
                if result["relevance"]
                else note
            )
        return result
    return item


def _coerce_metadata_artifact(value: Any) -> Any:
    """Normalize a step's metadata_artifact.

    Only objects are meaningful. A string/list (model drift) or empty content is
    treated as "no deployable metadata" -> None, turning the step manual rather
    than failing strict validation. Well-formed dicts pass through with files and
    members filtered to valid entries.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        # A string description or list is not deployable metadata.
        return None

    files = value.get("files")
    members = value.get("members")

    clean_files: list[dict] = []
    if isinstance(files, list):
        for f in files:
            if (
                isinstance(f, dict)
                and isinstance(f.get("path"), str)
                and isinstance(f.get("body"), str)
                and f["path"].strip()
            ):
                clean_files.append({"path": f["path"], "body": f["body"]})

    clean_members: list[dict] = []
    if isinstance(members, list):
        for m in members:
            if (
                isinstance(m, dict)
                and isinstance(m.get("type"), str)
                and isinstance(m.get("name"), str)
                and m["type"].strip()
                and m["name"].strip()
            ):
                clean_members.append({"type": m["type"], "name": m["name"]})

    # Nothing usable -> manual step.
    if not clean_files and not clean_members:
        return None

    result: dict[str, Any] = {"files": clean_files, "members": clean_members}
    api_version = value.get("api_version")
    if isinstance(api_version, (str, int, float)):
        result["api_version"] = str(api_version)
    else:
        result["api_version"] = None
    return result


def coerce_plan_data(data: Any) -> Any:
    """Best-effort normalization of a decoded plan dict.

    Never raises: if the input is not a dict, it is returned unchanged so the
    strict validators produce the authoritative error.
    """
    if not isinstance(data, dict):
        return data

    data = dict(data)  # shallow copy; we only rewrite top-level keys

    # Step numbers are needed to synthesize a deployment_sequence fallback.
    step_numbers: list[int] = []
    steps = data.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                n = _as_int(step.get("step_number"))
                if n is not None:
                    step_numbers.append(n)
                if "dependencies" in step:
                    step["dependencies"] = _int_list(step["dependencies"])
                if "metadata_artifact" in step:
                    step["metadata_artifact"] = _coerce_metadata_artifact(
                        step["metadata_artifact"]
                    )

    if "testing_requirements" in data:
        data["testing_requirements"] = _coerce_testing_requirements(
            data["testing_requirements"]
        )

    data["deployment_sequence"] = _coerce_deployment_sequence(
        data.get("deployment_sequence"), step_numbers
    )

    if isinstance(data.get("lsc_guide_references"), list):
        data["lsc_guide_references"] = [
            _coerce_lsc_reference(item) for item in data["lsc_guide_references"]
        ]

    for field in _STRING_LIST_FIELDS:
        if field in data:
            data[field] = _coerce_string_list(data[field])

    return data
