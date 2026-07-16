export type UserRole = "admin" | "analyst" | "viewer";
export type Severity = "critical" | "high" | "medium" | "low";
export type EntityType = "user" | "host";
export type AnomalyStatus = "new" | "investigating" | "incident" | "false_positive" | "closed";
export type AnalysisScope = "day" | "week" | "month" | "range" | "all";

export interface UserRead {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface FileValidationResult {
  is_valid: boolean;
  encoding: string | null;
  delimiter: string | null;
  columns: string[];
  missing_critical_columns: string[];
  errors: string[];
  sampled_rows: number;
}

export interface NormalizedArtifact {
  path: string;
  date: string;
  source: "SIEM" | "PAN";
  rows: number;
}

export interface NormalizationResult {
  artifacts?: NormalizedArtifact[];
  user_mapping_path?: string;
  processed_rows?: number;
  skipped_rows?: number;
  errors?: string[];
}

export interface UploadedFileRead {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  status: string;
  uploaded_by: string | null;
  created_at: string;
  validation_result: FileValidationResult | null;
  validated_at: string | null;
  normalization_result: NormalizationResult | null;
  normalized_at: string | null;
}

export interface AnalysisRunRead {
  id: string;
  status: string;
  scope: string;
  target_date: string | null;
  start_date: string | null;
  end_date: string | null;
  parameters: Record<string, unknown> | null;
  upload_ids: string[] | null;
  stages: Record<string, { status?: string; [key: string]: unknown }> | null;
  artifacts: Record<string, unknown> | null;
  current_stage: string | null;
  job_id: string | null;
  attempts: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AnomalyRead {
  id: string;
  run_id: string;
  entity_type: string;
  entity: string;
  date: string;
  severity: string;
  score: number;
  rank: number;
  summary: string;
  status: string;
  context: Record<string, unknown> | null;
  created_at: string;
}

export interface AnomalyExplanationRead {
  feature_name: string;
  feature_value: number;
  baseline_value: number;
  contribution: number;
}

export interface AnomalyActivityRead {
  id: string;
  actor_id: string | null;
  previous_status: string;
  new_status: string;
  comment: string | null;
  created_at: string;
}

export interface AnomalyDetail extends AnomalyRead {
  explanations: AnomalyExplanationRead[];
  activities: AnomalyActivityRead[];
}

export interface AnomalyList {
  items: AnomalyRead[];
  total: number;
  offset: number;
  limit: number;
  counters: Record<string, number>;
}

export interface ReportFileRead {
  format: string;
  filename: string;
  size: number;
  url: string;
}

export interface ReportRead {
  id: string;
  run_id: string;
  status: string;
  job_id: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  files: ReportFileRead[];
}

export interface Histogram {
  bin_edges: number[];
  counts: number[];
}

export interface StabilitySlice {
  compared_run: string | null;
  jaccard_at_k: number | null;
  overlap_at_k: number | null;
  spearman_at_k: number | null;
}

export interface ProxyMetricsRead {
  run_id: string;
  generated_at: string;
  score_distributions: { user: Histogram; host: Histogram };
  stability: { user: StabilitySlice; host: StabilitySlice };
  contributing_features: Record<string, number>;
}

export interface AuditEventRead {
  id: string;
  user_id: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  severity: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditEventList {
  items: AuditEventRead[];
  total: number;
  offset: number;
  limit: number;
}
