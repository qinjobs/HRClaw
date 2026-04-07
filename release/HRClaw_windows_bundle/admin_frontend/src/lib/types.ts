export interface JobOption {
  id: string;
  name: string;
  kind?: string;
  schema_version?: string;
  scorecard?: Record<string, unknown>;
  engine_type?: string;
  supports_resume_import?: boolean;
  editable?: boolean;
  system_managed?: boolean;
}

export interface SearchResultItem {
  rank: number;
  resume_profile_id: string;
  candidate_id?: string;
  source_candidate_id?: string | null;
  name?: string | null;
  city?: string | null;
  years_experience?: number | string | null;
  education_level?: string | null;
  latest_title?: string | null;
  latest_company?: string | null;
  retrieval_score?: number;
  fit_score?: number | null;
  total_score?: number;
  hard_filter_pass?: boolean;
  matched_evidence?: string[];
  gaps?: string[];
  risk_flags?: string[];
  interview_questions?: string[];
  final_recommendation?: string | null;
  explanation_status?: string | null;
  resume_entry?: Record<string, string>;
}

export interface SearchRunPayload {
  search_run_id: string;
  status: string;
  query_intent?: Record<string, unknown>;
  results: SearchResultItem[];
}

export interface ChecklistItem {
  candidate_id: string;
  task_id: string;
  job_id: string;
  job_name?: string | null;
  task_status?: string | null;
  task_started_at?: string | null;
  task_finished_at?: string | null;
  task_token_usage?: Record<string, number>;
  search_config?: Record<string, string>;
  external_id?: string | null;
  name?: string | null;
  age?: number | null;
  education_level?: string | null;
  years_experience?: number | null;
  current_company?: string | null;
  current_title?: string | null;
  expected_salary?: string | null;
  location?: string | null;
  total_score?: number | null;
  decision?: string | null;
  review_action?: string | null;
  final_decision?: string | null;
  reviewer?: string | null;
  greet_status?: string | null;
  screenshot_path?: string | null;
  gpt_extraction_used?: boolean | null;
  gpt_extraction_error?: string | null;
}

export interface WorkbenchItem {
  candidate_id: string;
  task_id: string;
  source: string;
  external_id?: string | null;
  extension_source_candidate_key?: string | null;
  name?: string | null;
  raw_summary?: string | null;
  age?: number | null;
  education_level?: string | null;
  years_experience?: number | null;
  current_company?: string | null;
  current_title?: string | null;
  expected_salary?: string | null;
  location?: string | null;
  candidate_created_at?: string | null;
  job_id: string;
  job_name?: string | null;
  task_status?: string | null;
  total_score?: number | null;
  decision?: string | null;
  review_reasons?: string[];
  hard_filter_fail_reasons?: string[];
  review_action?: string | null;
  review_final_decision?: string | null;
  reviewer?: string | null;
  greet_status?: string | null;
  screenshot_path?: string | null;
  pipeline_state?: Record<string, unknown>;
  tags?: string[];
}

export interface WorkbenchDetail {
  candidate: Record<string, any>;
  task: Record<string, any>;
  job: Record<string, any>;
  score: Record<string, any>;
  snapshot: Record<string, any>;
  pipeline_state: Record<string, any>;
  tags: Array<{ id: string; tag: string }>;
  timeline: Array<Record<string, any>>;
  review_actions?: Array<Record<string, any>>;
  reviews?: Array<Record<string, any>>;
  actions: Array<Record<string, any>>;
}

export interface Phase2ScorecardRecord {
  id: string;
  name: string;
  jd_text?: string;
  scorecard: Record<string, any>;
  kind?: string;
  scorecard_kind?: string;
  engine_type?: string;
  schema_version?: string;
  supports_resume_import?: boolean;
  editable?: boolean;
  system_managed?: boolean;
  active?: boolean;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ResumeImportBatch {
  id: string;
  scorecard_id: string;
  scorecard_name?: string | null;
  batch_name?: string | null;
  total_files?: number;
  processed_files?: number;
  recommend_count?: number;
  review_count?: number;
  reject_count?: number;
  created_at?: string;
  updated_at?: string;
  summary?: Record<string, unknown>;
}

export interface ResumeImportResult {
  id?: string;
  filename?: string | null;
  parse_status?: string | null;
  extracted_name?: string | null;
  location?: string | null;
  decision?: string | null;
  total_score?: number | null;
  years_experience?: number | null;
  education_level?: string | null;
  matched_terms?: string[];
  missing_terms?: string[];
  hard_filter_fail_reasons?: string[];
  summary?: string | null;
  resume_profile_id?: string | null;
}

export interface HrUser {
  id: string;
  username: string;
  display_name?: string;
  role: "admin" | "hr";
  active: boolean;
  notes?: string;
  last_login_at?: string | null;
  system_managed?: boolean;
  created_by?: string;
  updated_by?: string;
  created_at?: string | null;
  updated_at?: string | null;
}
