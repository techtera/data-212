"use client";

import { cn } from "@/lib/utils";
import { useJobStore } from "@/store/jobStore";
import type { Stage } from "@/types/job";


interface BannerSpec {
  text: (s: ReturnType<typeof useJobStore.getState>) => string;
  accent: "blue" | "amber" | "green" | "red" | "muted" | "pulse-green";
  visible: (s: ReturnType<typeof useJobStore.getState>) => boolean;
}

const SPECS: Record<Stage, BannerSpec> = {
  pre_masking: {
    text: (s) =>
      s.job?.progress != null
        ? `Running pretrained checkpoint on images... (${s.job.progress}%)`
        : "Running pretrained checkpoint on images...",
    accent: "pulse-green",
    visible: () => true,
  },
  awaiting_annotation: {
    text: (s) => {
      const a = s.job?.annotated_count ?? 0;
      const n = s.job?.unannotated_count ?? 0;
      return `Annotate low-confidence masks (${a}/${a + n} done)`;
    },
    accent: "amber",
    visible: () => true,
  },
  awaiting_approval: {
    text: () => "Awaiting research + risk-tier decision",
    accent: "red",
    visible: () => true,
  },
  training: {
    text: (s) =>
      s.job?.epoch && s.job?.total_epochs
        ? `Training... epoch ${s.job.epoch}/${s.job.total_epochs}`
        : "Training...",
    accent: "pulse-green",
    visible: () => true,
  },
  done: {
    text: () => "Job complete — see Results / Inference",
    accent: "green",
    visible: () => true,
  },
  rejected: {
    text: () => "Job rejected by reviewer",
    accent: "muted",
    visible: () => true,
  },
  error: {
    text: (s) => s.job?.log_excerpt ?? "Job failed — see Logs",
    accent: "red",
    visible: () => true,
  },
};

const ACCENT_CLASSES: Record<BannerSpec["accent"], string> = {
  blue: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  amber: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  green: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  red: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  "pulse-green":
    "border-emerald-500/40 bg-emerald-500/10 text-emerald-200 animate-pulse",
  muted: "border-zinc-500/40 bg-zinc-500/10 text-zinc-300",
};

export function StageBanner() {
  const stage = useJobStore((s) => s.job?.stage ?? null);
  const state = useJobStore.getState();

  if (!stage) {
    return (
      <div
        className={cn(
          "mb-3 rounded-md border px-3 py-2 text-sm",
          "border-zinc-700 bg-zinc-900/40 text-zinc-300"
        )}
      >
        No active job. Use the Train tab to start one.
      </div>
    );
  }

  const spec = SPECS[stage];
  if (!spec || !spec.visible(state)) return null;

  return (
    <div
      data-stage={stage}
      className={cn(
        "mb-3 rounded-md border px-3 py-2 text-sm font-medium",
        ACCENT_CLASSES[spec.accent]
      )}
    >
      {spec.text(state)}
    </div>
  );
}
