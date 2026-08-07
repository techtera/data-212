"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { SamplePredictionsGrid } from "@/components/charts/SamplePredictionsGrid";
import type { ResultsResponse } from "@/types/metrics";

const riskTierColors: Record<string, "default" | "destructive" | "warning" | "success" | "info"> = {
  low: "success",
  medium: "warning",
  high: "destructive",
  auto: "info",
};

export function ResultsTab() {
  const activeJobId = useJobStore((s) => s.activeJobId);
  const job = useJobStore((s) => s.job);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchResults = async () => {
    if (!activeJobId) return;
    setLoading(true);
    try {
      const data = await api.getResults(activeJobId);
      setResults(data);
    } catch {
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (job?.stage !== "done") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResults(null);
      return;
    }
    fetchResults();
  }, [activeJobId, job?.stage]);

  if (job?.stage !== "done") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Results</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-center py-8 text-muted-foreground">
            Final metrics & predictions appear when job reaches <code className="bg-zinc-800 px-1 rounded">done</code> stage.
          </p>
        </CardContent>
      </Card>
    );
  }

  const m = results?.final_metrics;
  const riskTier = results?.risk_tier ?? "auto";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Results</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className={cn("rounded-lg border p-4", `border-${riskTier}-500/30 bg-${riskTier}-500/5`)}>
          <div className="flex items-center gap-3 mb-2">
            <Badge variant={riskTierColors[riskTier]}>Risk Tier: {riskTier}</Badge>
            <span className="text-sm text-muted-foreground">{results?.risk_reasoning}</span>
          </div>
        </div>

        {m && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="rounded-lg border bg-card p-4">
              <p className="text-sm text-muted-foreground">Val Loss</p>
              <p className="text-2xl font-bold tabular-nums">{m.loss_val.toFixed(4)}</p>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <p className="text-sm text-muted-foreground">Accuracy</p>
              <p className="text-2xl font-bold tabular-nums">{(m.acc * 100).toFixed(1)}%</p>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <p className="text-sm text-muted-foreground">IoU</p>
              <p className="text-2xl font-bold tabular-nums">{(m.iou * 100).toFixed(1)}%</p>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <p className="text-sm text-muted-foreground">Dice</p>
              <p className="text-2xl font-bold tabular-nums">{(m.dice * 100).toFixed(1)}%</p>
            </div>
            <div className="rounded-lg border bg-card p-4 sm:col-span-2">
              <p className="text-sm text-muted-foreground">Epochs Completed</p>
              <p className="text-2xl font-bold tabular-nums">{m.epochs}</p>
            </div>
            <div className="rounded-lg border bg-card p-4 sm:col-span-2">
              <p className="text-sm text-muted-foreground">Total Runtime</p>
              <p className="text-2xl font-bold tabular-nums">{m.total_minutes} min</p>
            </div>
          </div>
        )}

        <div className="pt-4 border-t">
          <h3 className="mb-3 text-lg font-semibold">Sample Predictions</h3>
          <SamplePredictionsGrid predictions={results?.sample_predictions ?? []} />
        </div>

        <div className="pt-4 border-t">
          <p className="text-sm text-muted-foreground">
            For inference code and checkpoint download, see the <strong>Inference</strong> tab.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}