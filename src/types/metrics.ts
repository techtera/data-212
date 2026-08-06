export interface EpochMetrics {
  epoch: number;
  loss_tr: number;
  loss_val: number;
  acc: number;
  iou: number;
  dice: number;
}

export interface LogLine {
  ts: string;
  level: "info" | "warn" | "error";
  msg: string;
}

export interface LogsResponse {
  lines: LogLine[];
  epochs: EpochMetrics[];
}

export interface ComputeSample {
  vram_used_mb: number;
  vram_total_mb: number;
  gpu_util_pct: number;
  quota_remaining_jobs: number;
  quota_remaining_minutes: number;
  ts: string;
}

export interface FinalMetrics {
  loss_val: number;
  acc: number;
  iou: number;
  dice: number;
  epochs: number;
  total_minutes: number;
}

export interface SamplePrediction {
  image_url: string;
  pred_mask_url: string;
  gt_mask_url: string;
}

export interface ResultsResponse {
  final_metrics: FinalMetrics;
  sample_predictions: SamplePrediction[];
  risk_tier: "low" | "medium" | "high" | "auto";
  risk_reasoning: string;
}

export interface InferenceResponse {
  code: string;
  checkpoint_signed_url: string;
}
