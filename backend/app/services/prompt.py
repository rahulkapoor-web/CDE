"""System prompt loading and user-prompt (context) assembly."""

from datetime import datetime, timezone
from pathlib import Path

from app.schemas.planning import PlanningContext

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "ona_system_prompt.md"


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _bullets(items: list[str]) -> str:
    return "\n".join(f"  - {i}" for i in items) if items else "  - (none)"


def build_user_prompt(
    ctx: PlanningContext, guide_context: str = "", has_images: bool = False
) -> str:
    """Assemble the runtime user prompt with all context variables filled."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    plan_id = f"ONA-{ctx.jira_ticket_id or 'UNKNOWN'}-{timestamp}"

    guide_block = (
        f"\nRETRIEVED LSC GUIDE EXCERPTS (use to ground references):\n{guide_context}\n"
        if guide_context.strip()
        else "\nNo LSC guide excerpts retrieved. Use your knowledge; where uncertain, "
        'write "Verify in LSC Configuration Guide: [topic]".\n'
    )

    design_block = (
        "\nDESIGN REFERENCE: One or more UI design images (e.g. a Figma export) "
        "are attached. Treat them as the target UI. Derive required fields, "
        "components, layouts, labels, and interactions from the design and "
        "reflect them in the plan's steps and acceptance checks. Where the "
        "design implies Salesforce metadata (fields, page layouts, Lightning "
        "components), specify it explicitly.\n"
        if has_images
        else ""
    )

    return f"""INPUTS PROVIDED TO YOU

JIRA Ticket ID:       {ctx.jira_ticket_id}
Ticket Summary:       {ctx.jira_summary}
Ticket Description:   {ctx.jira_description}
Acceptance Criteria:  {ctx.jira_acceptance_criteria}
Ticket Type:          {ctx.jira_type}
Priority:             {ctx.jira_priority}

Current Org Edition:  {ctx.sf_org_edition}
LSC Modules Active:   {", ".join(ctx.lsc_modules) or "(unknown)"}
Installed Packages:   {", ".join(ctx.installed_packages) or "(unknown)"}
Org Metadata Snapshot:
  - Relevant objects:
{_bullets(ctx.metadata_objects)}
  - Relevant fields:
{_bullets(ctx.metadata_fields)}
  - Relevant flows:
{_bullets(ctx.metadata_flows)}
  - Relevant classes:
{_bullets(ctx.metadata_apex_classes)}
  - Permission sets:
{_bullets(ctx.metadata_permission_sets)}

GitHub Repo State:
  - Branch:             {ctx.github_branch}
  - Recent commits:
{_bullets(ctx.github_recent_commits)}
  - Open PRs:
{_bullets(ctx.github_open_prs)}
{guide_block}{design_block}
Use plan_id = "{plan_id}" and jira_ticket = "{ctx.jira_ticket_id}".
Return ONLY the JSON object, with no surrounding text or code fences."""
