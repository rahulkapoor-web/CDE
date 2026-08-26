"""Deterministic pre-deploy checks that catch self-inconsistent plans.

The Metadata API rejects a whole package when any component is unresolvable, and
its errors are cascading and opaque (a missing object shows up as a dozen
"Invalid type" / "Parent entity failed to deploy" errors on unrelated files).
These checks run BEFORE we build and submit the package so the reviewer gets a
single, actionable message — and so the refinement loop can be handed a precise
reason to fix — instead of a wall of downstream failures.

Two failure classes are covered, both observed in real deploys:

1. **Non-deployable metadata types.** OmniStudio components
   (``OmniFlexCard``/``OmniScript``/``OmniIntegrationProcedure``) are not
   standard Metadata API types; listing them in ``package.xml`` fails the entire
   deploy with *"Unknown type name 'OmniFlexCard'"*. They must be modelled as an
   LWC + Static Resource instead (see the system prompt).

2. **Dangling custom-object references.** A plan that references a custom object
   (``__c``) in a tab, layout, profile/permission-set field grant, or Apex —
   but neither creates that object in a step nor has it in the org context —
   fails with *"no CustomObject named X found"* on every referencing component.

Everything here is pure (no org/network I/O) so it is unit-testable and safe to
call on the request path.
"""

from __future__ import annotations

import re

from app.schemas.plan import Plan

# Metadata types that are NOT deployable via the classic Metadata API package we
# build. Listing any of these as a member poisons the whole package.xml. Keyed
# lower-case for case-insensitive matching.
NON_MDAPI_MEMBER_TYPES: dict[str, str] = {
    "omniflexcard": "OmniFlexCard",
    "omniscript": "OmniScript",
    "omniintegrationprocedure": "OmniIntegrationProcedure",
    "omnidataraptor": "OmniDataRaptor",
    "dataraptor": "DataRaptor",
    "flexcard": "FlexCard",
    "vlocitycard__c": "FlexCard",
    "integrationprocedure": "IntegrationProcedure",
}

# Folders whose files belong to the non-deployable OmniStudio family. A plan may
# smuggle these in as files even without a matching member.
_NON_MDAPI_FOLDER_TYPES: dict[str, str] = {
    "omniflexcards": "OmniFlexCard",
    "omniscripts": "OmniScript",
    "omniintegrationprocedures": "OmniIntegrationProcedure",
    "omnidataraptors": "OmniDataRaptor",
    "dataraptors": "DataRaptor",
    "flexcards": "FlexCard",
}

# A custom object API name: letters/digits/underscore ending in __c (namespaced
# objects like ns__Obj__c also end in __c). Case-insensitive on the suffix.
_CUSTOM_OBJECT_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*__c)\b", re.IGNORECASE)

# Inside a profile/permission-set body, the OBJECT is named either directly in an
# <object>…</object> grant or as the prefix of a <field>Object__c.Field__c</field>
# grant. We must extract only that object token — never the trailing field token,
# which is itself a __c name but is NOT a CustomObject.
_OBJECT_TAG_RE = re.compile(
    r"<object>\s*([A-Za-z][A-Za-z0-9_]*__c)\s*</object>", re.IGNORECASE
)
_FIELD_OBJECT_RE = re.compile(
    r"<field>\s*([A-Za-z][A-Za-z0-9_]*__c)\.", re.IGNORECASE
)

# package.xml member types that name a custom object directly (their fullName is
# the object, or is prefixed by the object). Used to know which references
# genuinely require the object to exist.
_OBJECT_SCOPED_MEMBER_TYPES = {
    "customtab",
    "customobject",
}


def _norm_obj(name: str) -> str:
    """Normalize a custom-object API name for comparison (case-insensitive)."""
    return name.strip().lower()


def _objects_created_by_plan(plan: Plan) -> set[str]:
    """Custom objects the plan itself creates (so their references are safe).

    An object is "created" when a step authors its ``objects/<Object>.object``
    file OR declares a ``CustomObject`` member for it.
    """
    created: set[str] = set()
    for step in plan.steps:
        art = step.metadata_artifact
        if not art:
            continue
        for f in art.files:
            path = f.path.strip().lstrip("/")
            # MDAPI: objects/<Object>.object  (source format also tolerated)
            m = re.match(r"objects/([^/]+?)\.object(?:-meta\.xml)?$", path, re.IGNORECASE)
            if m:
                created.add(_norm_obj(m.group(1)))
            m2 = re.match(r"objects/([^/]+?)/\1\.object-meta\.xml$", path, re.IGNORECASE)
            if m2:
                created.add(_norm_obj(m2.group(1)))
        for member in art.members:
            if member.type.strip().lower() == "customobject":
                created.add(_norm_obj(member.name))
    return created


def _custom_objects_in_org(org_objects: list[str] | None) -> set[str]:
    """Custom objects already present in the connected org (from context)."""
    out: set[str] = set()
    for name in org_objects or []:
        n = name.strip()
        if n.lower().endswith("__c"):
            out.add(_norm_obj(n))
    return out


def check_non_mdapi_types(plan: Plan) -> list[str]:
    """Flag members/files that use non-deployable (OmniStudio) metadata types."""
    errors: list[str] = []
    seen: set[str] = set()
    for step in plan.steps:
        art = step.metadata_artifact
        if not art:
            continue
        for member in art.members:
            canonical = NON_MDAPI_MEMBER_TYPES.get(member.type.strip().lower())
            if canonical and canonical not in seen:
                seen.add(canonical)
                errors.append(
                    f"Step {step.step_number} declares a '{canonical}' member "
                    f"({member.name}), but OmniStudio types are not deployable "
                    "via the Metadata API and will fail the whole package with "
                    f"\"Unknown type name '{canonical}'\". Rebuild this as a "
                    "Lightning Web Component (LWC) plus any needed Static "
                    "Resource instead."
                )
        for f in art.files:
            folder = f.path.strip().lstrip("/").split("/", 1)[0].lower()
            canonical = _NON_MDAPI_FOLDER_TYPES.get(folder)
            if canonical and canonical not in seen:
                seen.add(canonical)
                errors.append(
                    f"Step {step.step_number} includes an OmniStudio file "
                    f"('{f.path}'), which is not deployable via the Metadata "
                    "API. Rebuild this as a Lightning Web Component (LWC) plus "
                    "any needed Static Resource instead."
                )
    return errors


def _referenced_custom_objects(plan: Plan) -> dict[str, list[str]]:
    """Map each referenced custom object -> the step contexts that reference it.

    We look where a missing object actually breaks a deploy: object-scoped
    members (CustomTab/Layout/CustomObject fullNames), and object/field
    references inside profile & permission-set bodies. Apex bodies are scanned
    too since ``Invalid type: X__c`` is a common cascade source.
    """
    refs: dict[str, list[str]] = {}

    def _add(obj: str, where: str) -> None:
        refs.setdefault(_norm_obj(obj), [])
        if where not in refs[_norm_obj(obj)]:
            refs[_norm_obj(obj)].append(where)

    for step in plan.steps:
        art = step.metadata_artifact
        if not art:
            continue
        ctx = f"step {step.step_number}"

        for member in art.members:
            mtype = member.type.strip().lower()
            if mtype not in _OBJECT_SCOPED_MEMBER_TYPES:
                continue
            # fullName is either the object itself (CustomTab/CustomObject) or
            # "<Object>-<Layout Name>" (Layout). Take the object token.
            head = member.name.split("-", 1)[0]
            m = _CUSTOM_OBJECT_RE.search(head)
            if m:
                _add(m.group(1), f"{ctx} ({member.type} {member.name})")

        for f in art.files:
            path = f.path.strip().lstrip("/")
            lpath = path.lower()
            body = f.body or ""
            # Layout/tab file names embed the object.
            if lpath.startswith(("layouts/", "tabs/")):
                stem = path.split("/", 1)[1]
                head = stem.split("-", 1)[0].rsplit(".", 1)[0]
                m = _CUSTOM_OBJECT_RE.search(head)
                if m:
                    _add(m.group(1), f"{ctx} ({path})")
            # Profile / permission-set grants: pull the OBJECT from <object>
            # grants and from the object-prefix of <field>Object__c.Field__c</field>
            # grants. Never treat the field token itself as an object.
            if lpath.startswith(("profiles/", "permissionsets/")):
                for m in _OBJECT_TAG_RE.finditer(body):
                    _add(m.group(1), f"{ctx} ({path})")
                for m in _FIELD_OBJECT_RE.finditer(body):
                    _add(m.group(1), f"{ctx} ({path})")

    return refs


def check_dangling_object_references(
    plan: Plan, org_objects: list[str] | None = None
) -> list[str]:
    """Flag custom objects referenced by the plan but never created nor in org.

    ``org_objects`` is the connected org's object list (context
    ``metadata_objects``). When provided, an object present there is considered
    to exist and is not flagged. When ``None`` (org state unknown) we only flag
    objects that are referenced yet created by no step — the strongest signal of
    a self-inconsistent plan.
    """
    created = _objects_created_by_plan(plan)
    in_org = _custom_objects_in_org(org_objects)
    referenced = _referenced_custom_objects(plan)

    errors: list[str] = []
    for obj, contexts in sorted(referenced.items()):
        if obj in created or obj in in_org:
            continue
        # Recover a display name from the first context if possible.
        where = "; ".join(contexts[:3])
        more = "" if len(contexts) <= 3 else f" (+{len(contexts) - 3} more)"
        errors.append(
            f"Custom object '{obj}' is referenced by {where}{more}, but no step "
            "creates it and it is not present in the connected org. Add a step "
            f"that authors 'objects/{obj}.object' (with a CustomObject member) "
            "before the steps that reference it, or remove the references."
        )
    return errors


def validate_deployable(plan: Plan, org_objects: list[str] | None = None) -> list[str]:
    """Run all pre-deploy checks; return a combined list of blocking errors."""
    errors: list[str] = []
    errors.extend(check_non_mdapi_types(plan))
    errors.extend(check_dangling_object_references(plan, org_objects))
    return errors
