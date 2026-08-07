"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LossChart } from "@/components/charts/LossChart";
import { MetricsChart } from "@/components/charts/MetricsChart";
import { LogTail } from "@/components/charts/LogTail";
import { cn } from "@/lib/utils";
import type { LogsResponse } from "@/types/metrics";

export function LogsTab() {
  const activeJobId = useJobStore((s) => s.activeJobId);
  const job = useJobStore((s) => s.job);
  const [logs, setLogs] = useState<LogsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchLogs = async () => {
    if (!activeJobId) return;
    setLoading(true);
    try {
      const data = await api.getLogs(activeJobId);
      setLogs(data);
    } catch {
      setLogs(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (job?.stage !== "training" && job?.stage !== "done") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLogs(null);
      return;
    }
    fetchLogs();
    const timer = setInterval(fetchLogs, 3000);
    return () => clearInterval(timer);
  }, [activeJobId, job?.stage]);

  if (job?.stage !== "training" && job?.stage !== "done") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Logs</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-center py-8 text-muted-foreground">
            Live metrics & log tail stream during <code className="bg-zinc-800 px-1 rounded">training</code>
            and persist at <code className="bg-zinc-800 px-1 rounded">done</code>.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Logs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Tabs defaultValue="loss" className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="loss">Loss</TabsTrigger>
            <TabsTrigger value="metrics">Metrics</TabsTrigger>
            <TabsTrigger value="log">Log Tail</TabsTrigger>
          </TabsList>

          <TabsContent value="loss" className="mt-4">
            {loading ? (
              <p className="text-center py-8 text-muted-foreground">Loading…</p>
            ) : logs ? (
              <LossChart data={logs.epochs} />
            ) : (
              <p className="text-center py-8 text-muted-foreground">No data</p>
            )}
          </TabsContent>

          <TabsContent value="metrics" className="mt-4">
            {loading ? (
              <p className="text-center py-8 text-muted-foreground">Loading…</p>
            ) : logs ? (
              <MetricsChart data={logs.epochs} />
            ) : (
              <p className="text-center py-8 text-muted-foreground">No data</p>
            )}
          </TabsContent>

          <TabsContent value="log" className="mt-4">
            <LogTail lines={logs?.lines ?? []} maxLines={200} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}