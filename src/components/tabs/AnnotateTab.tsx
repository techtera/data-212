"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobStore } from "@/store/jobStore";
import { AnnotatorWrapper } from "@/components/Annotator";

export function AnnotateTab() {
  const stage = useJobStore((s) => s.job?.stage ?? null);
  const annotated = useJobStore((s) => s.job?.annotated_count ?? 0);
  const total =
    annotated + (useJobStore((s) => s.job?.unannotated_count ?? 0));

  if (stage !== "awaiting_annotation") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Annotate</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This tab becomes active when the job reaches the{" "}
            <code className="bg-zinc-800 px-1 rounded">awaiting_annotation</code>
            stage. Current stage:{stage && " "}{stage || "none"}
          </p>
        </CardContent>
      </Card>
    );
  }

  return <AnnotatorWrapper />;
}