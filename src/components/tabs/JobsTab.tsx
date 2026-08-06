"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobStore } from "@/store/jobStore";

export function JobsTab() {
  const activeJobId = useJobStore((s) => s.activeJobId);
  const stage = useJobStore((s) => s.job?.stage ?? null);
  const prompt = useJobStore((s) => s.prompt);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Jobs</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Real job table lands in M3. Store preview:
        </p>
        <pre className="mt-2 overflow-auto rounded bg-zinc-900 p-3 text-xs">
{JSON.stringify(
  { activeJobId, stage, prompt: prompt.slice(0, 60) },
  null,
  2
)}
        </pre>
      </CardContent>
    </Card>
  );
}
