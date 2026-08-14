"use client";

import * as React from "react";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

interface ApprovalModalProps {
  open: boolean;
  onClose: () => void;
  jobId: string;
}

const riskTierColors: Record<string, "default" | "destructive" | "warning" | "success" | "info"> = {
  low: "success",
  medium: "warning",
  high: "destructive",
  auto: "info",
};

export function ApprovalModal({ open, onClose, jobId }: ApprovalModalProps) {
  // Read research findings directly from the job store (populated by backend via polling)
  const researchFindings = useJobStore((s) => s.job?.research_findings);
  const riskTier = useJobStore((s) => s.job?.risk_tier ?? "auto");
  const riskReasoning = useJobStore((s) => s.job?.risk_reasoning);
  const [loading, setLoading] = React.useState(false);

  // Parse findings to extract recommended architecture
  const parsedFindings = React.useMemo(() => {
    if (!researchFindings) return { analysis: "", architecture: "", reasoning: "", config: "" };
    const lines = researchFindings.split("\n");
    let analysis = "";
    let architecture = "";
    let reasoning = "";
    let config = "";
    let section = "analysis";

    for (const line of lines) {
      if (line.startsWith("RECOMMENDED ARCHITECTURE:")) {
        architecture = line.replace("RECOMMENDED ARCHITECTURE:", "").trim();
        section = "arch";
      } else if (line.startsWith("REASONING:")) {
        reasoning = line.replace("REASONING:", "").trim();
        section = "reasoning";
      } else if (line.startsWith("PROPOSED CONFIG OVERRIDES:")) {
        config = line.replace("PROPOSED CONFIG OVERRIDES:", "").trim();
        section = "config";
      } else if (section === "analysis") {
        analysis += line + "\n";
      } else if (section === "reasoning" && line.trim()) {
        reasoning += " " + line.trim();
      } else if (section === "config") {
        config += line + "\n";
      }
    }
    return { analysis: analysis.trim(), architecture, reasoning: reasoning.trim(), config: config.trim() };
  }, [researchFindings]);

  const handleApprove = async () => {
    setLoading(true);
    try {
      await api.approve(jobId);
      toast.success("Job approved — training started");
      onClose();
    } catch (e) {
      toast.error(`Approve failed: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await api.reject(jobId);
      toast.warning("Job rejected");
      onClose();
    } catch (e) {
      toast.error(`Reject failed: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="max-w-2xl [&>button]:hidden">
        <DialogHeader>
          <DialogTitle>Approval Required</DialogTitle>
          <DialogDescription>
            Research agent has completed its analysis. Review the findings below and approve or reject.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4 max-h-[60vh] overflow-y-auto">
          {parsedFindings.architecture && (
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3">
              <h4 className="mb-1 font-semibold text-emerald-300">Recommended Architecture</h4>
              <p className="text-lg font-bold text-emerald-100">{parsedFindings.architecture}</p>
              {parsedFindings.reasoning && (
                <p className="mt-2 text-sm text-emerald-200/80">{parsedFindings.reasoning}</p>
              )}
            </div>
          )}

          <div>
            <h4 className="mb-2 font-medium">Analysis</h4>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {parsedFindings.analysis || researchFindings || "Loading research findings..."}
            </p>
          </div>

          {parsedFindings.config && (
            <div>
              <h4 className="mb-2 font-medium">Proposed Config</h4>
              <pre className="text-xs bg-zinc-900 rounded p-2 overflow-x-auto text-zinc-300">
                {parsedFindings.config}
              </pre>
            </div>
          )}

          <div>
            <h4 className="mb-2 font-medium">Risk Assessment</h4>
            <div className="flex items-center gap-3">
              <Badge variant={riskTierColors[riskTier] ?? "info"}>Risk Tier: {riskTier}</Badge>
              <span className="text-sm text-muted-foreground">
                {riskReasoning || "Score derived from model complexity, data sensitivity, and deployment context."}
              </span>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="destructive" onClick={handleReject} disabled={loading}>
            Reject
          </Button>
          <Button onClick={handleApprove} disabled={loading}>
            {loading ? "Approving..." : "Approve"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}