"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";

type Log = { ts: string; label: string; data: unknown };

export default function DebugPage() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [running, setRunning] = useState(false);
  const activeJobId = useJobStore((s) => s.activeJobId);

  function push(label: string, data: unknown) {
    setLogs((prev) => [...prev, { ts: new Date().toISOString(), label, data }]);
  }

  async function runAll() {
    if (running) return;
    setRunning(true);
    setLogs([]);

    try {
      const sign = await api.signUpload();
      push("POST /uploads/sign", sign);

      const created = await api.createJob({
        prompt: "train a model on my dataset",
        dataset_object_path: sign.object_path,
      });
      push("POST /jobs", created);
      const id = created.job_id;

      // M2: also seed the Zustand store so the home page banner
      // (which polls the same job) starts tracking this id.
      useJobStore.getState().setActiveJobId(id);
      useJobStore.getState().setPrompt("train a model on my dataset");

      await new Promise((r) => setTimeout(r, 500));
      const stage0 = await api.getJob(id);
      push("GET /jobs/{id} (initial)", stage0);

      // Wait long enough for the auto-advance to land on awaiting_annotation.
      await new Promise((r) => setTimeout(r, 4200));
      const stage1 = await api.getJob(id);
      push("GET /jobs/{id} (after 4s)", stage1);

      const flagged = await api.getFlagged(id);
      push("GET /jobs/{id}/flagged", flagged);

      const preview = await api.getDataPreview(id);
      push("GET /jobs/{id}/data-preview", preview);

      const annot = await api.sendAnnotations(
        id,
        new Blob(["coco-mock"], { type: "application/zip" })
      );
      push("POST /jobs/{id}/annotations", annot);

      const stage2 = await api.getJob(id);
      push("GET /jobs/{id} (after annot upload)", stage2);

      const approve = await api.approve(id);
      push("POST /jobs/{id}/approve", approve);

      const compute = await api.getCompute(id);
      push("GET /jobs/{id}/compute", compute);

      const logs = await api.getLogs(id);
      push("GET /jobs/{id}/logs", logs);

      const results = await api.getResults(id);
      push("GET /jobs/{id}/results", results);

      const inf = await api.getInference(id);
      push("GET /jobs/{id}/inference", inf);

      const list = await api.listJobs();
      push("GET /jobs", list);

      // Forcibly flip stage to training-advanced via autoAdvance poll loop.
      push("GET /jobs/{id} is poll-driven from the UI; stage advances every 4s", null);
    } catch (err) {
      push("ERROR", String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6">
      <h1 className="mb-2 text-2xl font-bold">M1 + M2 — mock backend & store verification</h1>
      <p className="mb-4 text-sm text-muted-foreground">
        Clicks each of the 13 mock endpoints in sequence. Each response below
        confirms MSW is intercepting + the state machine is advancing the job
        through stages. Also seeds the Zustand store so the home page
        &apos;s StageBanner starts polling this job.
      </p>
      <div className="mb-4 flex items-center gap-3">
        <button
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          onClick={runAll}
          disabled={running}
        >
          {running ? "running..." : "Run M1 endpoint sweep"}
        </button>
        <button
          className="rounded-md border border-border px-4 py-2 text-sm"
          onClick={() => {
            useJobStore.getState().setActiveJobId(null);
            setLogs([]);
          }}
          disabled={running}
        >
          Clear active job
        </button>
        {activeJobId ? (
          <span className="text-xs text-muted-foreground">
            active in store: <span className="font-mono">{activeJobId}</span>
          </span>
        ) : null}
      </div>
      <div className="space-y-2 font-mono text-xs">
        {logs.map((l, i) => (
          <div key={i} className="rounded border border-border p-2">
            <div className="text-muted-foreground">
              {l.ts} — {l.label}
            </div>
            <pre className="overflow-auto">{JSON.stringify(l.data, null, 2)}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}
