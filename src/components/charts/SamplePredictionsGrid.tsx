"use client";

import { cn } from "@/lib/utils";
import type { SamplePrediction } from "@/types/metrics";

interface SamplePredictionsGridProps {
  predictions: SamplePrediction[];
  className?: string;
}

export function SamplePredictionsGrid({ predictions, className }: SamplePredictionsGridProps) {
  if (predictions.length === 0) {
    return <p className={cn("text-center py-8 text-muted-foreground", className)}>No sample predictions</p>;
  }

  return (
    <div className={cn("space-y-4", className)}>
      {predictions.map((pred, i) => (
        <div key={i} className="grid grid-cols-3 gap-3">
          <figure className="relative aspect-square rounded border overflow-hidden bg-zinc-900">
            <img
              src={pred.image_url}
              alt={`Input ${i + 1}`}
              className="w-full h-full object-cover"
              loading="lazy"
            />
            <figcaption className="absolute bottom-0 left-0 right-0 px-2 py-1 bg-black/60 text-xs text-center text-white">
              Input
            </figcaption>
          </figure>
          <figure className="relative aspect-square rounded border overflow-hidden bg-zinc-900">
            <img
              src={pred.pred_mask_url}
              alt={`Predicted mask ${i + 1}`}
              className="w-full h-full object-cover"
              loading="lazy"
            />
            <figcaption className="absolute bottom-0 left-0 right-0 px-2 py-1 bg-black/60 text-xs text-center text-white">
              Predicted Mask
            </figcaption>
          </figure>
          <figure className="relative aspect-square rounded border overflow-hidden bg-zinc-900">
            <img
              src={pred.gt_mask_url}
              alt={`Ground truth mask ${i + 1}`}
              className="w-full h-full object-cover"
              loading="lazy"
            />
            <figcaption className="absolute bottom-0 left-0 right-0 px-2 py-1 bg-black/60 text-xs text-center text-white">
              Ground Truth
            </figcaption>
          </figure>
        </div>
      ))}
    </div>
  );
}