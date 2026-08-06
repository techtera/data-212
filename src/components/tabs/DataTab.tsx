"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobStore } from "@/store/jobStore";

export function DataTab() {
  const jobId = useJobStore((s) => s.activeJobId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Data</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          32-image preview grid lands in M5. Currently:{" "}
          {jobId ? `job ${jobId} is active` : "no active job"}.
        </p>
      </CardContent>
    </Card>
  );
}
