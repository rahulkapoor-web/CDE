import type { PlanJson } from "../types";

export function downloadFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function planToJson(plan: PlanJson): string {
  return JSON.stringify(plan, null, 2);
}

export function planToMarkdown(plan: PlanJson): string {
  const lines: string[] = [];
  lines.push(`# Plan ${plan.plan_id}`);
  lines.push("");
  lines.push(`**JIRA:** ${plan.jira_ticket}`);
  lines.push(`**Summary:** ${plan.summary}`);
  lines.push(`**Classification:** ${plan.change_classification}`);
  lines.push(`**Risk:** ${plan.deployment_risk} — ${plan.risk_rationale}`);
  lines.push(`**Estimated effort:** ${plan.estimated_effort}`);
  lines.push("");

  if (plan.prerequisites.length) {
    lines.push("## Prerequisites");
    plan.prerequisites.forEach((p) => lines.push(`- ${p}`));
    lines.push("");
  }

  if (plan.lsc_guide_references.length) {
    lines.push("## LSC Guide References");
    plan.lsc_guide_references.forEach((r) =>
      lines.push(`- **${r.module} → ${r.section}** (${r.page_or_url}): ${r.relevance}`),
    );
    lines.push("");
  }

  lines.push("## Steps");
  plan.steps.forEach((s) => {
    lines.push(`### ${s.step_number}. ${s.title}`);
    lines.push(`- **Type:** ${s.type} | **Env:** ${s.environment} | **Automation:** ${s.automation_feasibility}`);
    lines.push(`- **Description:** ${s.description}`);
    lines.push(`- **Acceptance check:** ${s.acceptance_check}`);
    if (s.metadata_path) lines.push(`- **Metadata path:** \`${s.metadata_path}\``);
    if (s.lsc_guide_reference) lines.push(`- **LSC ref:** ${s.lsc_guide_reference}`);
    if (s.dependencies.length) lines.push(`- **Depends on:** ${s.dependencies.join(", ")}`);
    if (s.rollback) lines.push(`- **Rollback:** ${s.rollback}`);
    lines.push(`- **Est. minutes:** ${s.estimated_minutes}`);
    lines.push("");
  });

  lines.push("## Testing Requirements");
  lines.push(`- **Unit tests:** ${plan.testing_requirements.unit_tests}`);
  lines.push(`- **Functional tests:** ${plan.testing_requirements.functional_tests}`);
  lines.push(`- **Regression areas:** ${plan.testing_requirements.regression_areas}`);
  lines.push(`- **Min coverage:** ${plan.testing_requirements.minimum_code_coverage}%`);
  lines.push("");

  lines.push("## Deployment Sequence");
  lines.push(`- **Sandbox:** ${plan.deployment_sequence.sandbox_steps.join(", ") || "—"}`);
  lines.push(`- **Production:** ${plan.deployment_sequence.production_steps.join(", ") || "—"}`);
  lines.push(`- **GitHub Actions:** ${plan.deployment_sequence.github_actions_steps.join(", ") || "—"}`);
  lines.push("");

  if (plan.post_deployment.length) {
    lines.push("## Post-Deployment");
    plan.post_deployment.forEach((p) => lines.push(`- ${p}`));
    lines.push("");
  }

  if (plan.open_questions.length) {
    lines.push("## Open Questions");
    plan.open_questions.forEach((q) => lines.push(`- ${q}`));
    lines.push("");
  }

  return lines.join("\n");
}
