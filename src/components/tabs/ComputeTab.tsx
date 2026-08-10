"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import { VramGauge } from "@/components/charts/VramGauge";
import { GpuUtilLine } from "@/components/charts/GpuUtilLine";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ComputeSample } from "@/types/metrics";

export function ComputeTab() {
  const activeJobId = useJobStore((s) => s.activeJobId);
  const job = useJobStore((s) => s.job);

  const [compute, setCompute] = useState<ComputeSample | null>(null);
  const [history, setHistory] = useState<ComputeSample[]>([]);
  const [loading, setLoading] = useState(false);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const historyRef = useRef<ComputeSample[]>([]);

  const fetchCompute = useCallback(async () => {
    if (!activeJobId) return;
    setLoading(true);
    try {
      const data = await api.getCompute(activeJobId);
      setCompute(data);
      historyRef.current = [...historyRef.current, data].slice(-60);
      setHistory([...historyRef.current]);
    } catch {
      setCompute(null);
    } finally {
      setLoading(false);
    }
  }, [activeJobId]);

  useEffect(() => {
    if (job?.stage !== "training") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCompute(null);
      historyRef.current = [];
      setHistory([]);
      return;
    }
    fetchCompute();
    timerRef.current = setInterval(fetchCompute, 3000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [activeJobId, job?.stage, fetchCompute]);

  const pct = compute?.vram_total_mb ? Math.round((compute.vram_used_mb / compute.vram_total_mb) * 100) : 0;
  const vramColor = pct >= 90 ? "destructive" : pct >= 70 ? "warning" : "default";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Compute</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {job?.stage !== "training" && (
          <div className="text-center py-8 text-muted-foreground">
            Compute metrics stream live only during <code className="bg-zinc-800 px-1 rounded">training</code> stage.
          </div>
        )}

        {job?.stage === "training" && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col items-center">
                <VramGauge usedMb={compute?.vram_used_mb ?? 0} totalMb={compute?.vram_total_mb ?? 24000} />
                <p className="mt-2 text-sm text-muted-foreground">VRAM Utilization</p>
              </div>

              <div className="md:col-span-2">
                <p className="mb-2 text-sm text-muted-foreground">GPU Utilization (rolling window)</p>
                <GpuUtilLine data={history} maxPoints={60} />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <div className="rounded-lg border bg-card p-4">
                <p className="text-sm text-muted-foreground">Quota: Remaining Jobs</p>
                <p className="text-3xl font-bold tabular-nums">{compute?.quota_remaining_jobs ?? 18}</p>
              </div>
              <div className="rounded-lg border bg-card p-4">
                <p className="text-sm text-muted-foreground">Quota: Remaining Minutes</p>
                <p className="text-3xl font-bold tabular-nums">{compute?.quota_remaining_minutes ?? 480}</p>
              </div>
            </div>

            <div className="flex items-center gap-2 text-sm">
              <Badge variant={vramColor}>VRAM {pct}%</Badge>
              <Badge variant="default">GPU {compute?.gpu_util_pct ?? 0}%</Badge>
              <span className="text-muted-foreground">Updated {compute?.ts ? new Date(compute.ts).toLocaleTimeString() : "—"}</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}