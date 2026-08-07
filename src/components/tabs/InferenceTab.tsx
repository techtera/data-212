"use client";

import * as React from "react";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/code-block";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export function InferenceTab() {
  const activeJobId = useJobStore((s) => s.activeJobId);
  const job = useJobStore((s) => s.job);
  const [inference, setInference] = React.useState<{ code: string; checkpoint_signed_url: string } | null>(null);
  const [loading, setLoading] = React.useState(false);

  const fetchInference = React.useCallback(async () => {
    if (!activeJobId) return;
    setLoading(true);
    try {
      const data = await api.getInference(activeJobId);
      setInference(data);
    } catch {
      setInference(null);
    } finally {
      setLoading(false);
    }
  }, [activeJobId]);

  React.useEffect(() => {
    if (job?.stage === "done") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchInference();
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setInference(null);
    }
  }, [activeJobId, job?.stage, fetchInference]);

  const handleCheckpointDownload = () => {
    if (!inference?.checkpoint_signed_url) return;
    // In dev, the signed URL points to /mock-data/checkpoint-mock.pt
    const a = document.createElement("a");
    a.href = inference.checkpoint_signed_url;
    a.download = "best.pt";
    a.click();
    toast.success("Checkpoint download started");
  };

  if (job?.stage !== "done") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Inference</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-center py-8 text-muted-foreground">
            Inference code & checkpoint appear when job reaches <code className="bg-zinc-800 px-1 rounded">done</code> stage.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Inference</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <h3 className="mb-3 text-lg font-semibold">Inference Script</h3>
          {loading ? (
            <p className="text-center py-8 text-muted-foreground">Loading…</p>
          ) : inference ? (
            <CodeBlock code={inference.code} language="python" />
          ) : (
            <p className="text-center py-8 text-muted-foreground">No inference script available.</p>
          )}
        </div>

        <div className="pt-4 border-t space-y-3">
          <h3 className="text-lg font-semibold">Checkpoint</h3>
          <p className="text-sm text-muted-foreground">
            Download the trained model weights (<code className="bg-zinc-800 px-1 rounded">best.pt</code>). The link is a short-lived signed URL.
          </p>
          <Button onClick={handleCheckpointDownload} disabled={loading || !inference?.checkpoint_signed_url}>
            {loading ? "Preparing…" : "Download checkpoint (.pt)"}
          </Button>
        </div>

        <div className="pt-4 border-t text-sm text-muted-foreground">
          <p>Run locally:</p>
          <pre className="mt-2 p-3 bg-zinc-950 rounded font-mono text-xs overflow-x-auto"><code>python inference.py --image path/to/image.jpg --checkpoint best.pt</code></pre>
        </div>
      </CardContent>
    </Card>
  );
}