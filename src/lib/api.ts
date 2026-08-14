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

/** Whether we are running in MSW mock mode */
const IS_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

function authHeaders(): Record<string, string> {
  // V1 dev auth: inject Bearer token when USE_MOCK=false and DEV_TOKEN is set.
  if (!IS_MOCK && process.env.NEXT_PUBLIC_DEV_TOKEN) {
    return { Authorization: `Bearer ${process.env.NEXT_PUBLIC_DEV_TOKEN}` };
  }
  return {};
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
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
  /**
   * Two-hop upload: sign → PUT to GCS.
   *
   * Security flow (per BLOCKDIAGRAM.txt):
   * 1. POST /uploads/sign (authenticated) → backend mints a time-boxed GCS
   *    signed PUT URL scoped to a single object (datasets/{id}/raw.zip).
   * 2. PUT the raw zip bytes directly to the signed URL. NO auth header is
   *    sent to GCS — the signature in the URL IS the credential.
   * 3. Returns { signed_put_url, object_path } so the caller can pass
   *    object_path to POST /jobs.
   *
   * The frontend NEVER constructs GCS URLs itself — only uses what the
   * backend returns. The session token never reaches GCS.
   */
  uploadDataset: async (file: File): Promise<UploadSignResponse> => {
    // Step 1: Get signed PUT URL from authenticated backend
    const signResult = await jsonFetch<UploadSignResponse>("/uploads/sign", {
      method: "POST",
    });

    // Step 2: PUT the raw file directly to GCS (or mock endpoint)
    // CRITICAL: No Authorization header — the signed URL IS the auth.
    // Content-Type must match what the backend specified when signing.
    const putRes = await fetch(signResult.signed_put_url, {
      method: "PUT",
      headers: {
        "Content-Type": "application/zip",
      },
      body: file,
    });

    if (!putRes.ok) {
      const text = await putRes.text().catch(() => "");
      throw new Error(`GCS upload failed ${putRes.status}: ${text}`);
    }

    return signResult;
  },

  // Legacy methods kept for MSW mock compatibility
  signUpload: () =>
    jsonFetch<UploadSignResponse>("/uploads/sign", { method: "POST" }),

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
