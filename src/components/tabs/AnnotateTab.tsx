"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobStore } from "@/store/jobStore";

export function AnnotateTab() {
  const stage = useJobStore((s) => s.job?.stage ?? null);
  const annotated = useJobStore((s) => s.job?.annotated_count ?? 0);
  const total =
    annotated +
    (useJobStore((s) => s.job?.unannotated_count ?? 0));
  const saved = Object.keys(useJobStore((s) => s.cocoMap)).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Annotate</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Real react-image-annotate + COCO export lands in M4. Store preview:
        </p>
        <pre className="mt-2 overflow-auto rounded bg-zinc-900 p-3 text-xs">
{JSON.stringify(
  { stage, annotated, total, locallySavedMasks: saved },
  null,
  2
)}
        </pre>
      </CardContent>
    </Card>
  );
}
