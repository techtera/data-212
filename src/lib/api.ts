import type {
  AnnotationsResponse,
  ApproveResponse,
  CreateJobRequest,
  CreateJobResponse,
  DataPreviewImage,
  FlaggedImage,
  JobProgress,
  JobSummary,
  RejectResponse,
  RerunResponse,
  UploadSignResponse,
} from "@/types/job";
import type {
  ComputeSample,
  InferenceResponse,
  LogsResponse,
  ResultsResponse,
} from "@/types/metrics";

const MOCK_BASE = "/api";
const PROD_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

export const API_BASE =
  process.env.NEXT_PUBLIC_USE_MOCK === "true" ? MOCK_BASE : PROD_BASE;

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${path}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  signUpload: () =>
    jsonFetch<UploadSignResponse>("/uploads/sign", { method: "POST" }),

  putRaw: (signedUrl: string, _bytes: File | Blob) => fetch(signedUrl, { method: "PUT", body: _bytes }),

  createJob: (req: CreateJobRequest) =>
    jsonFetch<CreateJobResponse>("/jobs", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  listJobs: () => jsonFetch<JobSummary[]>("/jobs"),

  getJob: (id: string) => jsonFetch<JobProgress>(`/jobs/${id}`),

  getFlagged: (id: string) =>
    jsonFetch<FlaggedImage[]>(`/jobs/${id}/flagged`),

  getDataPreview: (id: string) =>
    jsonFetch<DataPreviewImage[]>(`/jobs/${id}/data-preview`),

  sendAnnotations: (id: string, _zipBlob: Blob) =>
    jsonFetch<AnnotationsResponse>(`/jobs/${id}/annotations`, {
      method: "POST",
      body: JSON.stringify({ ack: true }),
    }),

  approve: (id: string) =>
    jsonFetch<ApproveResponse>(`/jobs/${id}/approve`, { method: "POST" }),

  reject: (id: string) =>
    jsonFetch<RejectResponse>(`/jobs/${id}/reject`, { method: "POST" }),

  rerun: (id: string) =>
    jsonFetch<RerunResponse>(`/jobs/${id}/rerun`, { method: "POST" }),

  getCompute: (id: string) =>
    jsonFetch<ComputeSample>(`/jobs/${id}/compute`),

  getLogs: (id: string) => jsonFetch<LogsResponse>(`/jobs/${id}/logs`),

  getResults: (id: string) =>
    jsonFetch<ResultsResponse>(`/jobs/${id}/results`),

  getInference: (id: string) =>
    jsonFetch<InferenceResponse>(`/jobs/${id}/inference`),
};
