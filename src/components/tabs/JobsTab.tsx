"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RiskBadge, StageBadge } from "@/components/StageBadges";
import { useJobStore } from "@/store/jobStore";
import { useNavStore } from "@/store/navStore";
import type { JobSummary } from "@/types/job";

export function JobsTab() {
  const setActiveJobId = useJobStore((s) => s.setActiveJobId);
  const setActiveTab = useNavStore((s) => s.setActiveTab);
  const activeJobId = useJobStore((s) => s.activeJobId);
  const setPrompt = useJobStore((s) => s.setPrompt);
  const resetAll = useJobStore((s) => s.resetAll);

  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [rerunning, setRerunning] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const list = await api.listJobs();
      setJobs([...list].reverse());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    queueMicrotask(() => {
      void refresh();
    });
  }, []);

  async function onRerun(id: string) {
    setRerunning(id);
    try {
      const out = await api.rerun(id);
      setActiveJobId(out.new_job_id);
      setActiveTab("annotate");
      await refresh();
    } finally {
      setRerunning(null);
    }
  }

  function onNewJob() {
    resetAll();
    setActiveTab("train");
  }

  function onSelect(j: JobSummary) {
    setActiveJobId(j.job_id);
    setPrompt(j.prompt);
    setActiveTab(j.stage === "awaiting_annotation" ? "annotate" : "logs");
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>Jobs</CardTitle>
          <CardDescription>
            All jobs you&apos;ve created. Click a row to make it active.
          </CardDescription>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            {loading ? "refreshing..." : "Refresh"}
          </Button>
          <Button size="sm" onClick={onNewJob}>
            New job
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No jobs yet. Click <strong>New job</strong> to start one.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job ID</TableHead>
                <TableHead>Prompt</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((j) => (
                <TableRow
                  key={j.job_id}
                  data-state={j.job_id === activeJobId ? "selected" : undefined}
                  className="cursor-pointer"
                  onClick={() => onSelect(j)}
                >
                  <TableCell className="font-mono">{j.job_id}</TableCell>
                  <TableCell className="max-w-[280px] truncate">
                    {j.prompt || <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <StageBadge stage={j.stage} />
                  </TableCell>
                  <TableCell>
                    <RiskBadge tier={j.risk_tier} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {new Date(j.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={rerunning === j.job_id}
                      onClick={(e) => {
                        e.stopPropagation();
                        void onRerun(j.job_id);
                      }}
                    >
                      {rerunning === j.job_id ? "rerunning..." : "Re-run"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
