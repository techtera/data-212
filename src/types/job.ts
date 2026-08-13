export type Stage =
  | "pre_masking"
  | "awaiting_annotation"
  | "researching"
  | "awaiting_approval"
  | "training"
  | "done"
  | "rejected"
  | "error";

export type RiskTier = "low" | "medium" | "high" | "auto";

export interface JobSummary {
  job_id: string;
  prompt: string;
  stage: Stage;
  risk_tier: RiskTier | null;
  created_at: string;
}

export interface FlaggedImage {
  image_id: string;
  url: string;
}

export interface DataPreviewImage {
  image_id: string;
  url: string;
}

export interface JobProgress {
  stage: Stage;
  progress: number;
  flagged?: FlaggedImage[];
  unannotated_count?: number;
  annotated_count?: number;
  epoch?: number;
  total_epochs?: number;
  stage_failed?: string;
  log_excerpt?: string;
  // V4: Research agent findings — populated after researching stage completes
  research_findings?: string;
  risk_tier?: string;
  risk_reasoning?: string;
}

export interface CreateJobRequest {
  prompt: string;
  dataset_object_path: string;
}

export interface CreateJobResponse {
  job_id: string;
  stage: Stage;
}

export interface UploadSignResponse {
  signed_put_url: string;
  object_path: string;
}

export interface ApproveResponse {
  stage: Stage;
}

export interface RejectResponse {
  stage: Stage;
}

export interface RerunResponse {
  new_job_id: string;
  stage: Stage;
}

export interface AnnotationsResponse {
  ok: boolean;
  stage: Stage;
}
