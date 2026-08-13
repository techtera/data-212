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
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Approval Required</DialogTitle>
          <DialogDescription>
            Research agent has completed its analysis. Review the findings below and approve or reject.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          <div>
            <h4 className="mb-2 font-medium">Research Findings</h4>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {researchFindings || "Loading research findings..."}
            </p>
          </div>

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
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
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