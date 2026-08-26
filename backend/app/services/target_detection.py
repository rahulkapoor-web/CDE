"""Detect which Salesforce objects a story actually touches.

The org describe returns hundreds of objects; retrieving layouts for all of them
is slow and floods the planner's context. Instead we scan the story text (JIRA
summary/description/acceptance criteria) for object API names that exist in the
org snapshot and scope layout retrieval to just those. This keeps the org pull
proportional to the change ("only what the story asks").

Pure functions, unit-tested.
"""

from __future__ import annotations

import re

# Standard objects a story commonly references by label rather than API name.
# Maps a lowercase word/label to the canonical API name.
_LABEL_ALIASES = {
    "account": "Account",
    "accounts": "Account",
    "contact": "Contact",
    "contacts": "Contact",
    "lead": "Lead",
    "leads": "Lead",
    "opportunity": "Opportunity",
    "opportunities": "Opportunity",
    "case": "Case",
    "cases": "Case",
    "user": "User",
    "users": "User",
}


def _tokenize(text: str) -> set[str]:
    """Return lowercased word tokens and candidate API-name tokens from text."""
    if not text:
        return set()
    # Keep tokens like Account, Health_Condition__c, Visit__c.
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]*(?:__c|__C)?", text)
    return {t for t in raw}


def detect_target_objects(text: str, known_objects: list[str]) -> list[str]:
    """Return org objects referenced by ``text``, preserving ``known_objects`` order.

    Matching is case-insensitive and considers:
      * exact API-name mentions (e.g. ``Health_Condition__c``, ``Account``)
      * common standard-object label aliases (e.g. "accounts" -> ``Account``)

    Returns an empty list when nothing matches, letting the caller decide on a
    fallback (e.g. use the full snapshot).
    """
    if not text or not known_objects:
        return []

    tokens = _tokenize(text)
    lower_tokens = {t.lower() for t in tokens}

    # Alias hits map to canonical API names.
    alias_hits = {
        api for word, api in _LABEL_ALIASES.items() if word in lower_tokens
    }

    matched: list[str] = []
    for obj in known_objects:
        obj_lower = obj.lower()
        if obj in tokens or obj_lower in lower_tokens or obj in alias_hits:
            matched.append(obj)

    return matched
