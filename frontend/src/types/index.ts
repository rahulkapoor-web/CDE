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

export type ConnType = "jira" | "github" | "salesforce" | "checklist";

export interface Connection {
  id: number;
  name: string;
  conn_type: ConnType;
  config: Record<string, unknown>;
  has_secrets: boolean;
  created_at: string;
}

export interface JiraImage {
  filename: string;
  media_type: string;
  data: string; // base64
}

export interface PlanningContext {
  jira_ticket_id: string;
  jira_summary: string;
  jira_description: string;
  jira_acceptance_criteria: string;
  jira_type: string;
  jira_priority: string;
  jira_images: JiraImage[];
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
  // Existing layout XML retrieved from the org, keyed by layout fullName. Not a
  // form field; carried through generate so the backend can merge layout_edits
  // into the real layout (preserving required items like Name).
  existing_layouts: Record<string, string>;
}

export interface LscGuideReference {
  module: string;
  section: string;
  page_or_url: string;
  relevance: string;
}

export interface MetadataFile {
  path: string;
  body: string;
}

export interface MetadataMember {
  type: string;
  name: string;
}

export interface MetadataArtifact {
  files: MetadataFile[];
  members: MetadataMember[];
  api_version?: string | null;
}

export interface PlanStep {
  step_number: number;
  title: string;
  type: string;
  environment: string;
  description: string;
  lsc_guide_reference?: string | null;
  metadata_path?: string | null;
  metadata_artifact?: MetadataArtifact | null;
  acceptance_check: string;
  estimated_minutes: number;
  automation_feasibility: string;
  automation_notes?: string | null;
  dependencies: number[];
  rollback?: string | null;
}

export interface DeployResult {
  state?: string | null;
  state_detail?: string | null;
  succeeded?: boolean;
  components_total?: string | null;
  components_deployed?: string | null;
  components_failed?: string | null;
  component_errors?: Array<Record<string, unknown>>;
  tests_total?: string | null;
  tests_failed?: string | null;
  test_errors?: Array<Record<string, unknown>>;
  async_id?: string;
  package_files?: string[];
  steps_included?: number[];
  check_only?: boolean;
  error?: string;
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
  assumed_prerequisites: string[];
  steps: PlanStep[];
  testing_requirements: {
    unit_tests: string;
    functional_tests: string;
    regression_areas: string;
    minimum_code_coverage: number;
  };
  deployment_sequence: {
    org_steps?: number[];
    github_actions_steps?: number[];
    // Legacy shape (pre connected-org model); still present on older stored
    // plans. Read via orgSteps() so the UI tolerates either shape.
    sandbox_steps?: number[];
    production_steps?: number[];
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
  approved_at?: string | null;
  approved_by_id?: number | null;
  deploy_connection_id?: number | null;
  deploy_async_id?: string | null;
  deploy_started_at?: string | null;
  deploy_finished_at?: string | null;
  deploy_result?: DeployResult | null;
}

export interface GithubCommitResult {
  branch: string;
  commit_sha: string;
  commit_url: string;
  branch_url: string;
  files: string[];
  created_branch: boolean;
  metadata_format: string;
}

export interface JiraCommentResult {
  ticket_id: string;
  comment_id: string | null;
  url: string;
}

export interface ChecklistItemResult {
  item: string;
  status: "pass" | "fail" | "partial" | "not_applicable";
  finding: string;
}

export interface ChecklistReviewResult {
  checklist_name: string;
  overall: "pass" | "fail" | "partial";
  summary: string;
  results: ChecklistItemResult[];
}

export interface PlanSummary {
  id: number;
  jira_ticket: string;
  summary: string | null;
  status: string;
  created_at: string;
}

/**
 * Steps applied to the connected org, tolerant of both the current shape
 * (`org_steps`) and the legacy shape (`sandbox_steps` + `production_steps`).
 * Older stored plans predate the connected-org model, so reading the raw field
 * directly can be undefined and crash the UI on `.join()`.
 */
export function orgSteps(ds: PlanJson["deployment_sequence"]): number[] {
  if (!ds) return [];
  if (Array.isArray(ds.org_steps)) return ds.org_steps;
  const legacy = [...(ds.sandbox_steps ?? []), ...(ds.production_steps ?? [])];
  return Array.from(new Set(legacy));
}

/** GitHub/CI steps, tolerant of a missing field on legacy plans. */
export function githubSteps(ds: PlanJson["deployment_sequence"]): number[] {
  return ds?.github_actions_steps ?? [];
}
