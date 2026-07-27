export interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string;
}

export interface ConnectionProfile {
  id: string;
  name: string;
  system_type: "salesforce" | "veeva_vault";
  environment: "sandbox" | "production";
  auth_method: string;
  sf_instance_url?: string;
  sf_username?: string;
  vault_dns?: string;
  vault_username?: string;
  created_at: string;
  updated_at: string;
}

export interface MigrationProject {
  id: string;
  name: string;
  description?: string;
  source_connection_id: string;
  target_connection_id: string;
  created_by: string;
  created_at: string;
}

export interface ObjectMapping {
  id: string;
  project_id: string;
  source_object: string;
  target_object: string;
  is_active: boolean;
  created_at: string;
}

export interface FieldMapping {
  id: string;
  object_mapping_id: string;
  source_field: string;
  target_field: string;
  source_field_type?: string;
  target_field_type?: string;
  transformation?: Record<string, unknown>;
  confidence_score?: number;
  is_auto_mapped: boolean;
  is_confirmed: boolean;
}

export interface MatchKeyConfig {
  id: string;
  object_mapping_id: string;
  source_field: string;
  target_field: string;
  key_order: number;
}

export interface SchemaField {
  name: string;
  label: string;
  field_type: string;
  is_required: boolean;
  is_unique: boolean;
  length?: number;
  picklist_values?: string[];
  reference_to?: string;
}

export interface SchemaObject {
  name: string;
  label: string;
  fields: SchemaField[];
  record_count?: number;
}

export interface AutoMappingSuggestion {
  source_field: string;
  target_field: string;
  source_field_type: string;
  target_field_type: string;
  confidence_score: number;
  match_reason: string;
}

export interface ValidationRun {
  id: string;
  project_id: string;
  user_id: string;
  status: "pending" | "queued" | "running" | "completed" | "failed" | "cancelled";
  mode: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
  object_mapping_ids?: string[];
  record_limit?: number;
  date_range_months?: number;
  source_where_clause?: string;
  total_objects: number;
  completed_objects: number;
  current_object_name?: string;
  progress_phase?: string;
  source_records_fetched: number;
  target_records_fetched: number;
  records_compared: number;
  total_records_to_compare: number;
}

export interface ValidationSummary {
  id: string;
  validation_run_id: string;
  object_mapping_id: string;
  source_object: string;
  target_object: string;
  source_count: number;
  target_count: number;
  matched_count: number;
  mismatched_count: number;
  missing_in_target_count: number;
  missing_in_source_count: number;
  match_percentage: number;
  status: string;
  error_message?: string;
}

export interface ValidationDetail {
  id: string;
  summary_id: string;
  match_key_value: string;
  status: string;
  field_diffs?: Record<
    string,
    { source: unknown; target: unknown; source_field: string; target_field: string }
  >;
}

export interface ValidationDetailPage {
  items: ValidationDetail[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
