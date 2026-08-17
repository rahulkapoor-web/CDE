export interface User {
  id: number;
  email: string;
  full_name?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export type ConnType = "jira" | "github" | "salesforce";

export interface Connection {
  id: number;
  name: string;
  conn_type: ConnType;
  config: Record<string, unknown>;
  has_secrets: boolean;
  created_at: string;
}

export interface PlanningContext {
  jira_ticket_id: string;
  jira_summary: string;
  jira_description: string;
  jira_acceptance_criteria: string;
  jira_type: string;
  jira_priority: string;
  sf_org_edition: string;
  lsc_modules: string[];
  installed_packages: string[];
  metadata_objects: string[];
  metadata_fields: string[];
  metadata_flows: string[];
  metadata_apex_classes: string[];
  metadata_permission_sets: string[];
  github_branch: string;
  github_recent_commits: string[];
  github_open_prs: string[];
}

export interface LscGuideReference {
  module: string;
  section: string;
  page_or_url: string;
  relevance: string;
}

export interface PlanStep {
  step_number: number;
  title: string;
  type: string;
  environment: string;
  description: string;
  lsc_guide_reference?: string | null;
  metadata_path?: string | null;
  acceptance_check: string;
  estimated_minutes: number;
  automation_feasibility: string;
  automation_notes?: string | null;
  dependencies: number[];
  rollback?: string | null;
}

export interface PlanJson {
  plan_id: string;
  jira_ticket: string;
  summary: string;
  change_classification: string;
  deployment_risk: string;
  risk_rationale: string;
  estimated_effort: string;
  lsc_guide_references: LscGuideReference[];
  prerequisites: string[];
  steps: PlanStep[];
  testing_requirements: {
    unit_tests: string;
    functional_tests: string;
    regression_areas: string;
    minimum_code_coverage: number;
  };
  deployment_sequence: {
    sandbox_steps: number[];
    production_steps: number[];
    github_actions_steps: number[];
  };
  post_deployment: string[];
  open_questions: string[];
  copilot_assist_available: boolean;
  copilot_suggested_actions: string[];
}

export interface Plan {
  id: number;
  jira_ticket: string;
  summary: string | null;
  status: string;
  provider: string | null;
  model: string | null;
  context_snapshot: PlanningContext;
  plan_json: PlanJson;
  created_at: string;
}

export interface PlanSummary {
  id: number;
  jira_ticket: string;
  summary: string | null;
  status: string;
  created_at: string;
}
