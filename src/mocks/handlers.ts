import { http, HttpResponse, delay } from "msw";

import type {
  ApproveResponse,
  AnnotationsResponse,
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

// =====================================================================
//  In-memory mock state.
//  Each job walks through stages automatically: on each `GET /jobs/{id}`
//  call, if 4s elapsed since last transition the stage advances by one
//  step along: pre_masking -> awaiting_annotation -> awaiting_approval
//  -> training -> done. POST /approve and /reject short-circuit the
//  awaiting_approval hop.
// =====================================================================

const STAGE_FLOW = [
  "pre_masking",
  "awaiting_annotation",
  "awaiting_approval",
  "training",
  "done",
] as const;

interface MockJob {
  job_id: string;
  prompt: string;
  stage: JobSummary["stage"];
  risk_tier: JobSummary["risk_tier"];
  created_at: string;
  last_transition_at: number;
  annotated_count: number;
  unannotated_count: number;
  epoch: number;
  total_epochs: number;
  dataset_object_path: string;
  annotations_uploaded: boolean;
}

const INITIAL_FLAGGED: FlaggedImage[] = [
  { image_id: "9", url: "/mock-data/flagged/9.png" },
  { image_id: "10", url: "/mock-data/flagged/10.png" },
  { image_id: "11", url: "/mock-data/flagged/11.png" },
  { image_id: "12", url: "/mock-data/flagged/12.png" },
];

const jobs = new Map<string, MockJob>();

let nextJobSeq = 1;
function makeJobId(): string {
  const id = `job_${String(nextJobSeq).padStart(3, "0")}`;
  nextJobSeq += 1;
  return id;
}

function seedJob(
  prompt: string,
  dataset_object_path: string
): MockJob {
  const now = Date.now();
  const flaggedN = INITIAL_FLAGGED.length;
  const job: MockJob = {
    job_id: makeJobId(),
    prompt,
    stage: "pre_masking",
    risk_tier: null,
    created_at: new Date(now).toISOString(),
    last_transition_at: now,
    annotated_count: 0,
    unannotated_count: flaggedN,
    epoch: 0,
    total_epochs: 10,
    dataset_object_path,
    annotations_uploaded: false,
  };
  jobs.set(job.job_id, job);
  return job;
}

function autoAdvance(j: MockJob) {
  const now = Date.now();
  if (now - j.last_transition_at < 4000) return;
  if (j.stage === "rejected" || j.stage === "error" || j.stage === "done") return;

  const nextIdx = STAGE_FLOW.indexOf(
    j.stage as (typeof STAGE_FLOW)[number]
  ) + 1;
  if (nextIdx < STAGE_FLOW.length) {
    j.stage = STAGE_FLOW[nextIdx];
    j.last_transition_at = now;
    if (j.stage === "awaiting_approval") {
      j.risk_tier = "medium";
    }
    if (j.stage === "training" && j.epoch === 0) {
      j.epoch = 1;
    }
  }
}

function getJobOr404(id: string) {
  const j = jobs.get(id);
  if (!j) {
    return HttpResponse.json(
      { detail: `job ${id} not found` },
      { status: 404 }
    );
  }
  return j;
}

function generateEpochMetrics(uptoEpoch: number) {
  const epochs = [];
  for (let e = 1; e <= uptoEpoch; e++) {
    epochs.push({
      epoch: e,
      loss_tr: +(1.0 - e * 0.08).toFixed(4),
      loss_val: +(1.0 - e * 0.06).toFixed(4),
      acc: +(0.5 + e * 0.04).toFixed(4),
      iou: +(0.3 + e * 0.05).toFixed(4),
      dice: +(0.4 + e * 0.045).toFixed(4),
    });
  }
  return epochs;
}

function generateLogLines(uptoEpoch: number) {
  const lines = [];
  for (let e = 1; e <= uptoEpoch; e++) {
    lines.push({
      ts: new Date(Date.now() - (uptoEpoch - e) * 5000).toISOString(),
      level: (e % 3 === 0 ? "warn" : "info") as "warn" | "info",
      msg: `epoch ${e} loss=${(1.0 - e * 0.08).toFixed(4)} val=${(
        1.0 -
        e * 0.06
      ).toFixed(4)}`,
    });
  }
  return lines;
}

function jobToSummary(j: MockJob): JobSummary {
  return {
    job_id: j.job_id,
    prompt: j.prompt,
    stage: j.stage,
    risk_tier: j.risk_tier,
    created_at: j.created_at,
  };
}

const base = "/api";

export const handlers = [
  http.post(`${base}/uploads/sign`, async () => {
    await delay(120);
    const id = `ds_${Date.now().toString(36)}`;
    const body: UploadSignResponse = {
      signed_put_url: `/mock-upload/${id}`,
      object_path: `datasets/${id}/raw.zip`,
    };
    return HttpResponse.json(body);
  }),

  http.put(`/mock-upload/:id`, async () => {
    await delay(80);
    return new HttpResponse(null, { status: 200 });
  }),

  http.post(`${base}/jobs`, async ({ request }) => {
    await delay(120);
    const req = (await request.json()) as CreateJobRequest;
    const job = seedJob(req.prompt, req.dataset_object_path);
    const body: CreateJobResponse = { job_id: job.job_id, stage: job.stage };
    return HttpResponse.json(body);
  }),

  http.get(`${base}/jobs`, () => {
    const summaries = [...jobs.values()].map(jobToSummary);
    return HttpResponse.json(summaries);
  }),

  http.get(`${base}/jobs/:id`, ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    autoAdvance(j);
    const progress: JobProgress = {
      stage: j.stage,
      progress:
        j.stage === "done"
          ? 100
          : j.stage === "training"
            ? Math.round((j.epoch / j.total_epochs) * 100)
            : j.stage === "pre_masking"
              ? 25
              : j.stage === "awaiting_annotation"
                ? 50
                : 75,
      epoch: j.stage === "training" ? j.epoch : undefined,
      total_epochs: j.stage === "training" ? j.total_epochs : undefined,
      unannotated_count:
        j.stage === "awaiting_annotation" ? j.unannotated_count : undefined,
      annotated_count:
        j.stage === "awaiting_annotation" ? j.annotated_count : undefined,
      flagged:
        j.stage === "awaiting_annotation" ? INITIAL_FLAGGED : undefined,
    };
    return HttpResponse.json(progress);
  }),

  http.get(`${base}/jobs/:id/flagged`, ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    return HttpResponse.json(INITIAL_FLAGGED);
  }),

  http.get(`${base}/jobs/:id/data-preview`, () => {
    const preview: DataPreviewImage[] = [];
    for (let i = 1; i <= 8; i++) {
      preview.push({ image_id: String(i), url: `/mock-data/images/${i}.png` });
    }
    return HttpResponse.json(preview);
  }),

  http.post(`${base}/jobs/:id/annotations`, async ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    await delay(150);
    j.annotations_uploaded = true;
    j.unannotated_count = 0;
    j.annotated_count = INITIAL_FLAGGED.length;
    j.stage = "awaiting_approval";
    j.last_transition_at = Date.now();
    const body: AnnotationsResponse = { ok: true, stage: j.stage };
    return HttpResponse.json(body);
  }),

  http.post(`${base}/jobs/:id/approve`, async ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    await delay(150);
    j.stage = "training";
    j.last_transition_at = Date.now();
    j.epoch = 1;
    const body: ApproveResponse = { stage: j.stage };
    return HttpResponse.json(body);
  }),

  http.post(`${base}/jobs/:id/reject`, async ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    await delay(150);
    j.stage = "rejected";
    j.last_transition_at = Date.now();
    const body: RejectResponse = { stage: j.stage };
    return HttpResponse.json(body);
  }),

  http.post(`${base}/jobs/:id/rerun`, async ({ params }) => {
    const id = params.id as string;
    const oldJob = getJobOr404(id);
    if (oldJob instanceof HttpResponse) return oldJob;
    await delay(150);
    const newJob = seedJob(oldJob.prompt, oldJob.dataset_object_path);
    const body: RerunResponse = {
      new_job_id: newJob.job_id,
      stage: newJob.stage,
    };
    return HttpResponse.json(body);
  }),

  http.get(`${base}/jobs/:id/compute`, ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    const sample: ComputeSample = {
      vram_used_mb:
        j.stage === "training" ? 18000 + Math.round(2000 * Math.random()) : 0,
      vram_total_mb: 24000,
      gpu_util_pct:
        j.stage === "training" ? 70 + Math.round(20 * Math.random()) : 0,
      quota_remaining_jobs: 18,
      quota_remaining_minutes: 480,
      ts: new Date().toISOString(),
    };
    return HttpResponse.json(sample);
  }),

  http.get(`${base}/jobs/:id/logs`, ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    const upTo = j.stage === "training" ? j.epoch : 10;
    const body: LogsResponse = {
      lines: generateLogLines(upTo),
      epochs: generateEpochMetrics(upTo),
    };
    return HttpResponse.json(body);
  }),

  http.get(`${base}/jobs/:id/results`, ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    const body: ResultsResponse = {
      final_metrics: {
        loss_val: 0.2143,
        acc: 0.92,
        iou: 0.78,
        dice: 0.85,
        epochs: 10,
        total_minutes: 12,
      },
      sample_predictions: [
        { image_url: "/mock-data/images/1.png", pred_mask_url: "/mock-data/images/1.png", gt_mask_url: "/mock-data/images/1.png" },
        { image_url: "/mock-data/images/2.png", pred_mask_url: "/mock-data/images/2.png", gt_mask_url: "/mock-data/images/2.png" },
        { image_url: "/mock-data/images/3.png", pred_mask_url: "/mock-data/images/3.png", gt_mask_url: "/mock-data/images/3.png" },
      ],
      risk_tier: "low",
      risk_reasoning: "Minor update to existing entry; research findings high-confidence.",
    };
    return HttpResponse.json(body);
  }),

  http.get(`${base}/jobs/:id/inference`, async ({ params }) => {
    const id = params.id as string;
    const j = getJobOr404(id);
    if (j instanceof HttpResponse) return j;
    const code = `import torch
from PIL import Image
import numpy as np

def load_checkpoint(path: str):
    return torch.load(path, map_location="cpu")

def predict(image_path: str, model):
    img = np.array(Image.open(image_path).convert("RGB"))
    return np.zeros(img.shape[:2], dtype=np.uint8)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--checkpoint", default="best.pt")
    args = p.parse_args()
    model = load_checkpoint(args.checkpoint)
    mask = predict(args.image, model)
    Image.fromarray(mask).save("pred_mask.png")
    print("saved pred_mask.png")
`;
    const body: InferenceResponse = {
      code,
      checkpoint_signed_url: "/mock-data/checkpoint-mock.pt",
    };
    return HttpResponse.json(body);
  }),
];
