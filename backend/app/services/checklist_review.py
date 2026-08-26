"""Review a generated plan against a project-scope checklist.

The checklist is a reusable rubric (stored as a ``checklist`` connection). This
service asks the LLM to judge the plan against each checklist item and return a
structured pass/fail/partial result per item plus an overall verdict.

Kept separate from planner.py so the review prompt and JSON contract evolve
independently of plan generation.
"""

from __future__ import annotations

import json
import logging
import re

from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)

_SYSTEM_PROMPT = (
    "You are a meticulous Salesforce release reviewer. You evaluate a change "
    "PLAN against a project CHECKLIST. Judge only what the plan states; do not "
    "invent work. Follow the checklist as authoritative guidelines. For each "
    "checklist item decide one status: 'pass' (the plan clearly satisfies it), "
    "'fail' (the plan violates it or omits something the item requires), "
    "'partial' (partially addressed), or 'not_applicable' (item does not apply "
    "to this change). Be specific and cite the relevant step or omission in the "
    "finding. Respond with JSON only."
)

_OUTPUT_CONTRACT = """
Return ONLY a JSON object with this exact shape:
{
  "overall": "pass" | "fail" | "partial",
  "summary": "one or two sentences on overall compliance",
  "results": [
    {
      "item": "<the checklist item text>",
      "status": "pass" | "fail" | "partial" | "not_applicable",
      "finding": "why, referencing the plan"
    }
  ]
}
overall = "fail" if any applicable item is "fail"; "partial" if any is
"partial" but none "fail"; otherwise "pass".
"""


def parse_checklist_items(text: str) -> list[str]:
    """Split raw checklist text into individual items.

    Accepts markdown bullets/numbering; strips list markers and blank lines.
    """
    items: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        # Strip common list markers: -, *, +, "1.", "1)", "[ ]", "[x]".
        s = re.sub(r"^[-*+]\s+", "", s)
        s = re.sub(r"^\d+[.)]\s+", "", s)
        s = re.sub(r"^\[[ xX]?\]\s+", "", s)
        if s:
            items.append(s)
    return items


def _extract_json(text: str) -> dict:
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1)
    return json.loads(text)


def _fallback_from_error(items: list[str], reason: str) -> dict:
    return {
        "overall": "partial",
        "summary": f"Automated review could not be parsed: {reason}",
        "results": [
            {"item": it, "status": "not_applicable", "finding": "not evaluated"}
            for it in items
        ],
    }


async def review_plan_against_checklist(
    provider: LLMProvider,
    plan_json: dict,
    checklist_text: str,
) -> dict:
    """Return a structured compliance review dict (see _OUTPUT_CONTRACT).

    Best-effort: on LLM/JSON failure returns a 'partial' verdict listing items
    as not-evaluated rather than raising, so the caller can still show something.
    """
    items = parse_checklist_items(checklist_text)
    if not items:
        return {
            "overall": "partial",
            "summary": "Checklist is empty; nothing to evaluate.",
            "results": [],
        }

    numbered = "\n".join(f"{i + 1}. {it}" for i, it in enumerate(items))
    plan_str = json.dumps(plan_json, indent=2, ensure_ascii=False)
    user_prompt = (
        "CHECKLIST (authoritative guidelines):\n"
        + numbered
        + "\n\nPLAN (JSON):\n"
        + plan_str
        + "\n"
        + _OUTPUT_CONTRACT
    )

    try:
        result = await provider.complete(
            _SYSTEM_PROMPT, user_prompt, max_tokens=4000, temperature=0.0
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Checklist review LLM call failed: %s", exc)
        return _fallback_from_error(items, str(exc))

    try:
        data = _extract_json(result.text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Checklist review JSON parse failed: %s", exc)
        return _fallback_from_error(items, "invalid JSON from model")

    # Normalize / guard the shape.
    results = data.get("results")
    if not isinstance(results, list) or not results:
        # Model returned prose or wrong shape; keep the items visible.
        data = _fallback_from_error(items, "model returned no per-item results")
        data["summary"] = data.get("summary") or "No per-item results returned."
    else:
        cleaned = []
        for r in results:
            if not isinstance(r, dict):
                continue
            cleaned.append(
                {
                    "item": str(r.get("item", "")).strip() or "(unnamed item)",
                    "status": str(r.get("status", "not_applicable")).strip().lower(),
                    "finding": str(r.get("finding", "")).strip(),
                }
            )
        data["results"] = cleaned

    overall = str(data.get("overall", "")).strip().lower()
    if overall not in {"pass", "fail", "partial"}:
        statuses = {r["status"] for r in data["results"]}
        if "fail" in statuses:
            overall = "fail"
        elif "partial" in statuses:
            overall = "partial"
        else:
            overall = "pass"
    data["overall"] = overall
    data["summary"] = str(data.get("summary", "")).strip()
    return data
