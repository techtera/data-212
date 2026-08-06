"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useJobStore } from "@/store/jobStore";

export function TrainTab() {
  const prompt = useJobStore((s) => s.prompt);
  const fileName = useJobStore((s) => s.uploadedFileName);
  const progress = useJobStore((s) => s.uploadProgress);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Train</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Real .zip upload + start-job flow lands in M3. Store preview:
        </p>
        <pre className="mt-2 overflow-auto rounded bg-zinc-900 p-3 text-xs">
{JSON.stringify(
  {
    prompt: prompt.slice(0, 60),
    uploadedFileName: fileName,
    uploadProgress: progress,
  },
  null,
  2
)}
        </pre>
      </CardContent>
    </Card>
  );
}
